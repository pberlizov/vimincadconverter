"""Versioned HTTP API for CAD integrations (uploads, jobs, artifacts, SSE)."""

from __future__ import annotations

import asyncio
import json
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from mesh2cad.api.security import require_api_key
from mesh2cad.api.service import process_mesh
from mesh2cad.api.v1.artifacts import (
    ARTIFACT_NAMES,
    artifact_filename,
    artifact_media_type,
    resolve_artifact_path,
)
from mesh2cad.api.v1.schemas import JobSubmitBodyV1, ProcessMeshBodyV1
from mesh2cad.domain.types import ToleranceConfig
from mesh2cad.jobs.runner import request_job_cancel, retry_job, submit_job
from mesh2cad.security.webhook_url import WebhookUrlRejected, validate_webhook_url
from mesh2cad.ui.db import (
    create_job_with_id,
    get_job,
    get_job_paths,
    idempotency_lookup,
    idempotency_register,
    initialize_database,
)
from mesh2cad.ui.state import get_max_upload_bytes, get_state_dir

router = APIRouter(prefix="/v1", tags=["v1"], dependencies=[Depends(require_api_key)])

_ALLOWED_SUFFIXES = frozenset({".stl", ".obj", ".ply", ".xyz", ".pts", ".csv", ".npy"})


def _sanitize_filename(filename: str) -> str:
    cleaned = Path(filename).name.replace("\x00", "")
    return cleaned or "upload.bin"


def _bool_form(v: Any, default: bool = True) -> bool:
    if v is None:
        return default
    s = str(v).strip().lower()
    if s in {"", "on", "true", "1", "yes"}:
        return True
    if s in {"off", "false", "0", "no"}:
        return False
    return default


async def _write_upload_limited(upload: UploadFile, dest: Path) -> None:
    max_bytes = get_max_upload_bytes()
    dest.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with dest.open("wb") as handle:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Uploaded file exceeds configured size limit.")
            handle.write(chunk)


def _process_options_from_body(body: ProcessMeshBodyV1) -> dict[str, Any]:
    """Options for jobs (JSON-serializable ``tolerances`` dict) and sync ``process_mesh`` (convert dict → domain)."""
    return {
        "sample_count": body.sample_count,
        "simplify_target_faces": body.simplify_target_faces,
        "build": body.build,
        "auto_tune_sampling": body.auto_tune_sampling,
        "align_surface_metrics": body.align_surface_metrics,
        "icp_iterations": body.icp_iterations,
        "icp_seed": body.icp_seed,
        "include_script": body.include_script,
        "tolerances": body.tolerances_dict(),
        "icp_hybrid_hull_weight": body.icp_hybrid_hull_weight,
    }


@router.post("/process")
async def v1_process(request: Request) -> dict[str, Any]:
    """Run pipeline synchronously. Send JSON or ``multipart/form-data`` with ``file``."""
    ct = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" in ct:
        form = await request.form()
        up = form.get("file")
        if not isinstance(up, UploadFile):
            raise HTTPException(status_code=400, detail="Multipart requests require a 'file' field.")
        safe = _sanitize_filename(up.filename or "mesh.stl")
        suffix = Path(safe).suffix.lower()
        if suffix not in _ALLOWED_SUFFIXES:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix!r}")
        sync_root = get_state_dir() / "v1_sync"
        sync_root.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix="proc_", dir=str(sync_root)))
        dest = tmp / safe
        await _write_upload_limited(up, dest)
        input_path = dest.resolve()
        body = JobSubmitBodyV1(
            input_path=input_path,
            output_dir=Path(form["output_dir"]).expanduser() if form.get("output_dir") else None,
            sample_count=int(form.get("sample_count") or 5000),
            simplify_target_faces=int(form["simplify_target_faces"])
            if form.get("simplify_target_faces")
            else None,
            build=_bool_form(form.get("build"), True),
            auto_tune_sampling=_bool_form(form.get("auto_tune_sampling"), True),
            align_surface_metrics=_bool_form(form.get("align_surface_metrics"), True),
            icp_iterations=int(form.get("icp_iterations") or 10),
            icp_seed=int(form.get("icp_seed") or 0),
            include_script=_bool_form(form.get("include_script"), True),
            tolerances=None,
            icp_hybrid_hull_weight=float(form["icp_hybrid_hull_weight"])
            if form.get("icp_hybrid_hull_weight") not in (None, "")
            else None,
        )
    else:
        try:
            raw = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Expected JSON body or multipart form.") from exc
        body = ProcessMeshBodyV1.model_validate(raw)

    opts = _process_options_from_body(body)
    inp = body.resolved_input_path()
    if not inp.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {inp}")
    out = body.resolved_output_dir() if body.build else None
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
    tol_dict = opts.get("tolerances")
    tc = ToleranceConfig(**tol_dict) if isinstance(tol_dict, dict) and tol_dict else None
    sync_opts = {**opts, "tolerances": tc}
    return process_mesh(
        input_path=inp,
        output_dir=out,
        **sync_opts,
    )


@router.post("/jobs")
async def v1_submit_job(
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    """Queue async job. JSON body and/or multipart ``file`` (same field names as ``/v1/process``)."""
    if idempotency_key:
        existing = idempotency_lookup(idempotency_key)
        if existing is not None:
            job = get_job(existing)
            return {
                "job_id": existing,
                "status": job["status"] if job else "unknown",
                "idempotent_replay": True,
            }

    job_id = uuid.uuid4().hex
    upload_dir, job_dir = get_job_paths(job_id)
    ct = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" in ct:
        form = await request.form()
        up = form.get("file")
        if not isinstance(up, UploadFile):
            raise HTTPException(status_code=400, detail="Multipart job submit requires a 'file' field.")
        safe = _sanitize_filename(up.filename or "mesh.stl")
        suffix = Path(safe).suffix.lower()
        if suffix not in _ALLOWED_SUFFIXES:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix!r}")
        dest = upload_dir / safe
        await _write_upload_limited(up, dest)
        input_path = dest.resolve()
        body = JobSubmitBodyV1(
            input_path=input_path,
            output_dir=Path(form["output_dir"]).expanduser() if form.get("output_dir") else None,
            sample_count=int(form.get("sample_count") or 5000),
            simplify_target_faces=int(form["simplify_target_faces"])
            if form.get("simplify_target_faces")
            else None,
            build=_bool_form(form.get("build"), True),
            auto_tune_sampling=_bool_form(form.get("auto_tune_sampling"), True),
            align_surface_metrics=_bool_form(form.get("align_surface_metrics"), True),
            icp_iterations=int(form.get("icp_iterations") or 10),
            icp_seed=int(form.get("icp_seed") or 0),
            include_script=_bool_form(form.get("include_script"), True),
            tolerances=None,
            icp_hybrid_hull_weight=float(form["icp_hybrid_hull_weight"])
            if form.get("icp_hybrid_hull_weight") not in (None, "")
            else None,
            webhook_url=(str(form["webhook_url"]).strip() if form.get("webhook_url") else None),
        )
    else:
        raw = await request.json()
        body = JobSubmitBodyV1.model_validate(raw)
        if body.input_path is None:
            raise HTTPException(status_code=400, detail="JSON job submit requires input_path on the server.")
        input_path = body.resolved_input_path()
        if not input_path.is_file():
            raise HTTPException(status_code=400, detail=f"Not a file: {input_path}")

    try:
        validate_webhook_url(body.webhook_url)
    except WebhookUrlRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    opts = _process_options_from_body(body)
    output_dir = body.resolved_output_dir() if body.build else None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    request_payload = {
        "input_path": str(input_path),
        "output_dir": str(output_dir) if output_dir else None,
        "sample_count": opts["sample_count"],
        "simplify_target_faces": opts["simplify_target_faces"],
        "build": opts["build"],
        "auto_tune_sampling": opts["auto_tune_sampling"],
        "align_surface_metrics": opts["align_surface_metrics"],
        "icp_iterations": opts["icp_iterations"],
        "icp_seed": opts["icp_seed"],
        "include_script": opts["include_script"],
        "tolerances": opts["tolerances"],
        "icp_hybrid_hull_weight": opts["icp_hybrid_hull_weight"],
        "webhook_url": str(body.webhook_url) if body.webhook_url else None,
    }

    create_job_with_id(
        job_id=job_id,
        user_id=0,
        original_name=input_path.name,
        input_path=input_path,
        output_dir=job_dir,
        request_payload=request_payload,
    )
    submit_job(
        job_id=job_id,
        input_path=input_path,
        output_dir=output_dir,
        artifact_dir=job_dir,
        sample_count=opts["sample_count"],
        simplify_target_faces=opts["simplify_target_faces"],
        build=opts["build"],
        auto_tune_sampling=opts["auto_tune_sampling"],
        align_surface_metrics=opts["align_surface_metrics"],
        icp_iterations=opts["icp_iterations"],
        icp_seed=opts["icp_seed"],
        include_script=opts["include_script"],
        tolerances=opts["tolerances"],
        icp_hybrid_hull_weight=opts["icp_hybrid_hull_weight"],
    )
    if idempotency_key:
        idempotency_register(idempotency_key, job_id)
    return {"job_id": job_id, "status": "queued", "idempotent_replay": False}


@router.get("/jobs/{job_id}")
def v1_job_status(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {
        "api_version": 1,
        "job_id": job["id"],
        "status": job["status"],
        "warnings": job.get("warnings", []),
        "payload": job.get("payload", {}),
        "step_path": job.get("step_path"),
    }


@router.get("/jobs/{job_id}/artifacts/{artifact_name}")
def v1_download_artifact(job_id: str, artifact_name: str) -> FileResponse:
    if artifact_name not in ARTIFACT_NAMES:
        raise HTTPException(status_code=404, detail="Unknown artifact name.")
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    _, job_dir = get_job_paths(job_id)
    path = resolve_artifact_path(job, job_dir, artifact_name)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found.")
    fname = artifact_filename(artifact_name, job)
    return FileResponse(
        path,
        filename=fname,
        media_type=artifact_media_type(artifact_name),
    )


@router.get("/jobs/{job_id}/events")
async def v1_job_events(job_id: str) -> StreamingResponse:
    """Server-sent events: ``status`` field until terminal state."""

    async def gen():
        while True:
            job = get_job(job_id)
            if job is None:
                yield f"data: {json.dumps({'error': 'not_found'})}\n\n"
                return
            payload = {"job_id": job_id, "status": job["status"]}
            yield f"data: {json.dumps(payload)}\n\n"
            if job["status"] in {"completed", "failed", "cancelled"}:
                return
            await asyncio.sleep(2.0)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/jobs/{job_id}/cancel")
def v1_cancel(job_id: str) -> dict[str, Any]:
    if get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    detail = request_job_cancel(job_id)
    return {
        "job_id": job_id,
        "status": detail["status"],
        "detail": detail.get("detail", ""),
    }


@router.post("/jobs/{job_id}/retry")
def v1_retry(job_id: str) -> dict[str, Any]:
    detail = retry_job(job_id)
    if detail["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Job not found.")
    if detail["status"] == "invalid_state":
        raise HTTPException(status_code=400, detail="Only terminal jobs can be retried.")
    if detail["status"] == "missing_request":
        raise HTTPException(status_code=400, detail="Original request not stored for this job.")
    return {"job_id": job_id, "status": "queued", "message": "Retry submitted."}


def health_router() -> APIRouter:
    """Unauthenticated probes (no API key)."""

    r = APIRouter(tags=["health"])

    @r.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @r.get("/ready")
    def ready() -> JSONResponse:
        initialize_database()
        try:
            from mesh2cad.ui.db import connect

            with connect() as conn:
                conn.execute("SELECT 1")
            from mesh2cad.ui.state import ensure_state_dirs

            ensure_state_dirs()
        except Exception as exc:
            return JSONResponse({"ready": False, "detail": str(exc)}, status_code=503)
        return JSONResponse({"ready": True})

    return r
