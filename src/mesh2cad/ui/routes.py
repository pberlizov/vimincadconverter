from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from mesh2cad.jobs.runner import request_job_cancel, retry_job, submit_job
from mesh2cad.ui.auth import generate_session_token, hash_password, verify_password
from mesh2cad.ui.db import (
    create_job_with_id,
    create_session,
    create_user,
    delete_session,
    get_job_for_user,
    get_job_paths,
    get_user_by_username,
    get_user_for_session,
    initialize_database,
    list_jobs_for_user,
    set_job_request,
    update_job,
    user_count,
)
from mesh2cad.ui.state import get_max_upload_bytes, use_secure_cookies


SESSION_COOKIE = "mesh2cad_session"
ALLOWED_INPUT_SUFFIXES = {".stl", ".obj", ".ply"}


def register_ui(app: FastAPI) -> None:
    initialize_database()
    app.mount(
        "/assets",
        StaticFiles(directory=Path(__file__).resolve().parent.joinpath("static")),
        name="assets",
    )
    app.include_router(create_ui_router())


def create_ui_router() -> APIRouter:
    router = APIRouter()
    templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.joinpath("templates")))

    @router.get("/", response_class=HTMLResponse)
    def index(request: Request):
        if user_count() == 0:
            return RedirectResponse(url="/setup", status_code=303)
        user = current_user_optional(request)
        if user is None:
            return RedirectResponse(url="/login", status_code=303)
        return RedirectResponse(url="/dashboard", status_code=303)

    @router.get("/setup", response_class=HTMLResponse)
    def setup_form(request: Request):
        if user_count() > 0:
            return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(
            request,
            "setup.html",
            {"request": request, "error": None, "title": "Initial Setup"},
        )

    @router.post("/setup")
    async def setup_submit(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
    ):
        if user_count() > 0:
            return RedirectResponse(url="/login", status_code=303)
        if len(username.strip()) < 3 or len(password) < 8:
            return templates.TemplateResponse(
                request,
                "setup.html",
                {
                    "request": request,
                    "error": "Username must be at least 3 characters and password at least 8 characters.",
                    "title": "Initial Setup",
                },
                status_code=400,
            )
        user = create_user(username.strip(), hash_password(password), is_admin=True)
        response = RedirectResponse(url="/dashboard", status_code=303)
        _sign_in(response, int(user["id"]))
        return response

    @router.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        if user_count() == 0:
            return RedirectResponse(url="/setup", status_code=303)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"request": request, "error": None, "title": "Sign In"},
        )

    @router.post("/login")
    async def login_submit(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
    ):
        user = get_user_by_username(username.strip())
        if user is None or not verify_password(password, str(user["password_hash"])):
            return templates.TemplateResponse(
                request,
                "login.html",
                {"request": request, "error": "Invalid credentials.", "title": "Sign In"},
                status_code=401,
            )
        response = RedirectResponse(url="/dashboard", status_code=303)
        _sign_in(response, int(user["id"]))
        return response

    @router.post("/logout")
    def logout(request: Request):
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            delete_session(token)
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @router.get("/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request, user: dict[str, Any] = Depends(require_user)):
        jobs = list_jobs_for_user(int(user["id"]))
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "request": request,
                "title": "ViminCADConverter Console",
                "user": user,
                "jobs": jobs,
            },
        )

    @router.post("/jobs")
    async def create_job_route(
        request: Request,
        source_file: UploadFile = File(...),
        sample_count: int = Form(5000),
        simplify_target_faces: str = Form(""),
        build: str | None = Form(None),
        auto_tune: str | None = Form("on"),
        user: dict[str, Any] = Depends(require_user),
    ):
        job_id = _persist_upload(user_id=int(user["id"]), source_file=source_file)
        upload_dir, job_dir = get_job_paths(job_id)
        input_path = _first_file(upload_dir)
        request_payload = {
            "input_path": str(input_path),
            "output_dir": str(job_dir) if build == "on" else None,
            "sample_count": sample_count,
            "simplify_target_faces": int(simplify_target_faces) if simplify_target_faces.strip() else None,
            "build": build == "on",
            "auto_tune_sampling": auto_tune == "on",
            "align_surface_metrics": True,
            "icp_iterations": 10,
            "icp_seed": 0,
        }
        set_job_request(job_id, request_payload)
        submit_job(
            job_id=job_id,
            input_path=input_path,
            output_dir=job_dir if build == "on" else None,
            artifact_dir=job_dir,
            sample_count=sample_count,
            simplify_target_faces=int(simplify_target_faces) if simplify_target_faces.strip() else None,
            build=build == "on",
            auto_tune_sampling=auto_tune == "on",
        )
        return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)

    @router.post("/jobs/{job_id}/cancel")
    def cancel_job_route(
        job_id: str,
        user: dict[str, Any] = Depends(require_user),
    ):
        job = get_job_for_user(job_id, int(user["id"]))
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        if job["status"] not in {"queued", "processing"}:
            raise HTTPException(status_code=400, detail="Only queued or processing jobs can be cancelled.")
        request_job_cancel(job_id)
        return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)

    @router.post("/jobs/{job_id}/retry")
    def retry_job_route(
        job_id: str,
        user: dict[str, Any] = Depends(require_user),
    ):
        job = get_job_for_user(job_id, int(user["id"]))
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        if job["status"] not in {"completed", "failed", "cancelled"}:
            raise HTTPException(status_code=400, detail="Only terminal jobs can be retried.")
        detail = retry_job(job_id)
        if detail["status"] != "queued":
            raise HTTPException(status_code=400, detail=f"Retry failed: {detail['detail']}")
        return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)

    @router.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_detail(request: Request, job_id: str, user: dict[str, Any] = Depends(require_user)):
        job = get_job_for_user(job_id, int(user["id"]))
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        input_name = Path(str(job.get("source_path") or "")).suffix.lower()
        input_preview_supported = input_name in {".stl", ".obj", ".ply"}
        generated_preview_available = bool((job.get("payload") or {}).get("build", {}).get("metadata", {}).get("preview_stl_path"))
        failure = (job.get("payload") or {}).get("failure")
        plan = (job.get("payload") or {}).get("reconstruction_plan")
        return templates.TemplateResponse(
            request,
            "job_detail.html",
            {
                "request": request,
                "title": f"Job {job_id}",
                "user": user,
                "job": job,
                "input_preview_supported": input_preview_supported,
                "generated_preview_available": generated_preview_available,
                "failure": failure,
                "reconstruction_plan": plan,
                "can_cancel": job["status"] in {"queued", "processing"},
                "can_retry": job["status"] in {"completed", "failed", "cancelled"},
            },
        )

    @router.get("/jobs/{job_id}/files/{artifact_name}")
    def download_artifact(
        job_id: str,
        artifact_name: str,
        user: dict[str, Any] = Depends(require_user),
    ):
        job = get_job_for_user(job_id, int(user["id"]))
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")

        _, job_dir = get_job_paths(job_id)
        artifact_path = _artifact_path(job, job_dir, artifact_name)
        if artifact_path is None or not artifact_path.exists():
            raise HTTPException(status_code=404, detail="Artifact not found.")
        return FileResponse(artifact_path)

    @router.get("/jobs/{job_id}/status")
    def job_status(job_id: str, user: dict[str, Any] = Depends(require_user)):
        job = get_job_for_user(job_id, int(user["id"]))
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        return {
            "id": job["id"],
            "status": job["status"],
            "step_path": job.get("step_path"),
            "warnings": job.get("warnings", []),
            "has_payload": bool(job.get("payload")),
        }

    return router


def current_user_optional(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return get_user_for_session(token)


def require_user(request: Request) -> dict[str, Any]:
    user = current_user_optional(request)
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def _sign_in(response: RedirectResponse, user_id: int) -> None:
    token = generate_session_token()
    create_session(token, user_id)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=use_secure_cookies(),
        path="/",
    )


def _persist_upload(*, user_id: int, source_file: UploadFile) -> str:
    safe_name = _sanitize_filename(source_file.filename or "upload.bin")
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_INPUT_SUFFIXES:
        raise HTTPException(status_code=400, detail="Unsupported file type.")

    temp_job_id = uuid.uuid4().hex
    upload_dir, job_dir = get_job_paths(temp_job_id)
    input_path = upload_dir.joinpath(safe_name)
    max_upload_bytes = get_max_upload_bytes()
    bytes_written = 0
    with input_path.open("wb") as handle:
        while True:
            chunk = source_file.file.read(1024 * 1024)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > max_upload_bytes:
                input_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Uploaded file exceeds configured size limit.")
            handle.write(chunk)
    create_job_with_id(
        job_id=temp_job_id,
        user_id=user_id,
        original_name=safe_name,
        input_path=input_path,
        output_dir=job_dir,
    )
    update_job(
        temp_job_id,
        status="queued",
        source_path=str(input_path),
        payload={"job_id": temp_job_id},
    )
    return temp_job_id


def _sanitize_filename(filename: str) -> str:
    cleaned = Path(filename).name.replace("\x00", "")
    return cleaned or "upload.bin"


def _first_file(directory: Path) -> Path:
    for path in directory.iterdir():
        if path.name.startswith("."):
            continue
        if path.is_file():
            return path
    raise FileNotFoundError(f"No uploaded file found in {directory}")


def _artifact_path(job: dict[str, Any], job_dir: Path, artifact_name: str) -> Path | None:
    if artifact_name == "report":
        return job_dir.joinpath("report.json")
    if artifact_name == "script":
        return job_dir.joinpath("reconstruction.py")
    if artifact_name == "step" and job.get("step_path"):
        return Path(str(job["step_path"]))
    if artifact_name == "preview":
        preview_path = (job.get("payload") or {}).get("build", {}).get("metadata", {}).get("preview_stl_path")
        if preview_path:
            return Path(str(preview_path))
    if artifact_name == "input" and job.get("source_path"):
        return Path(str(job["source_path"]))
    return None
