from __future__ import annotations

import os
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from pathlib import Path
import shutil
from threading import Lock
from typing import Any

from mesh2cad.jobs.webhook_delivery import schedule_job_webhook

from mesh2cad.jobs.exceptions import CANCEL_FILENAME, JobCancelledError, JobTimeoutError
from mesh2cad.jobs.worker_subprocess import run_cli_worker_subprocess
from mesh2cad.ui.db import get_job, get_job_paths, reset_job_for_retry, update_job

_EXECUTOR: ThreadPoolExecutor | None = None
_EXECUTOR_LOCK = Lock()
_FUTURES: dict[str, Future[dict[str, Any]]] = {}
_FUTURES_LOCK = Lock()


def submit_job(
    *,
    job_id: str,
    input_path: str | Path,
    output_dir: str | Path | None,
    artifact_dir: str | Path,
    sample_count: int,
    simplify_target_faces: int | None,
    build: bool,
    auto_tune_sampling: bool = True,
    align_surface_metrics: bool = True,
    icp_iterations: int = 10,
    icp_seed: int = 0,
    include_script: bool = True,
    tolerances: dict[str, Any] | None = None,
    icp_hybrid_hull_weight: float | None = None,
) -> Future[dict[str, Any]]:
    update_job(job_id, status="queued")
    future = _executor().submit(
        _run_job,
        job_id=job_id,
        input_path=str(input_path),
        output_dir=str(output_dir) if output_dir is not None else None,
        artifact_dir=str(artifact_dir),
        sample_count=sample_count,
        simplify_target_faces=simplify_target_faces,
        build=build,
        auto_tune_sampling=auto_tune_sampling,
        align_surface_metrics=align_surface_metrics,
        icp_iterations=icp_iterations,
        icp_seed=icp_seed,
        include_script=include_script,
        tolerances=tolerances,
        icp_hybrid_hull_weight=icp_hybrid_hull_weight,
    )
    with _FUTURES_LOCK:
        _FUTURES[job_id] = future
    future.add_done_callback(lambda completed: _finalize_future(job_id, completed))
    return future


def request_job_cancel(job_id: str) -> dict[str, str]:
    """Cancel a queued job if possible; otherwise write a marker for the running worker."""
    with _FUTURES_LOCK:
        fut = _FUTURES.get(job_id)
    if fut is not None and fut.cancel():
        return {"status": "cancelled", "detail": "removed_from_queue"}

    _, job_dir = get_job_paths(job_id)
    marker = Path(job_dir).joinpath(CANCEL_FILENAME)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch(exist_ok=True)
    update_job(job_id, status="cancelling")
    return {"status": "cancel_requested", "detail": "marker_written"}


def retry_job(job_id: str) -> dict[str, str]:
    job = get_job(job_id)
    if job is None:
        return {"status": "not_found", "detail": "missing_job"}
    if job["status"] not in {"failed", "cancelled", "completed"}:
        return {"status": "invalid_state", "detail": job["status"]}

    request = dict(job.get("request") or {})
    if not request:
        return {"status": "missing_request", "detail": "no_persisted_request"}

    reset = reset_job_for_retry(job_id)
    if reset is None:
        return {"status": "not_found", "detail": "missing_job"}

    upload_dir, job_dir = get_job_paths(job_id)
    _clear_retry_artifacts(job_dir)
    job_dir.joinpath(CANCEL_FILENAME).unlink(missing_ok=True)

    output_dir = job_dir if bool(request.get("build", True)) else None
    submit_job(
        job_id=job_id,
        input_path=str(reset["input_path"]),
        output_dir=output_dir,
        artifact_dir=job_dir,
        sample_count=int(request.get("sample_count", 5000)),
        simplify_target_faces=request.get("simplify_target_faces"),
        build=bool(request.get("build", True)),
        auto_tune_sampling=bool(request.get("auto_tune_sampling", True)),
        align_surface_metrics=bool(request.get("align_surface_metrics", True)),
        icp_iterations=int(request.get("icp_iterations", 10)),
        icp_seed=int(request.get("icp_seed", 0)),
        include_script=bool(request.get("include_script", True)),
        tolerances=request.get("tolerances") if isinstance(request.get("tolerances"), dict) else None,
        icp_hybrid_hull_weight=(
            float(request["icp_hybrid_hull_weight"])
            if request.get("icp_hybrid_hull_weight") is not None
            else None
        ),
    )
    return {"status": "queued", "detail": "retry_submitted"}


def get_job_future(job_id: str) -> Future[dict[str, Any]] | None:
    with _FUTURES_LOCK:
        return _FUTURES.get(job_id)


def _executor() -> ThreadPoolExecutor:
    global _EXECUTOR
    with _EXECUTOR_LOCK:
        if _EXECUTOR is None:
            try:
                workers = max(1, int(os.environ.get("MESH2CAD_JOB_WORKERS", "2")))
            except ValueError:
                workers = 2
            _EXECUTOR = ThreadPoolExecutor(
                max_workers=workers,
                thread_name_prefix="mesh2cad-job",
            )
    return _EXECUTOR


def _run_job(
    *,
    job_id: str,
    input_path: str,
    output_dir: str | None,
    artifact_dir: str,
    sample_count: int,
    simplify_target_faces: int | None,
    build: bool,
    auto_tune_sampling: bool,
    align_surface_metrics: bool = True,
    icp_iterations: int = 10,
    icp_seed: int = 0,
    include_script: bool = True,
    tolerances: dict[str, Any] | None = None,
    icp_hybrid_hull_weight: float | None = None,
) -> dict[str, Any]:
    update_job(job_id, status="processing")
    worker_request: dict[str, Any] = {
        "input_path": input_path,
        "output_dir": output_dir,
        "artifact_dir": artifact_dir,
        "sample_count": sample_count,
        "simplify_target_faces": simplify_target_faces,
        "build": build,
        "auto_tune_sampling": auto_tune_sampling,
        "align_surface_metrics": align_surface_metrics,
        "icp_iterations": icp_iterations,
        "icp_seed": icp_seed,
        "include_script": include_script,
        "tolerances": tolerances,
        "icp_hybrid_hull_weight": icp_hybrid_hull_weight,
    }
    payload = run_cli_worker_subprocess(worker_request=worker_request)
    update_job(
        job_id,
        status="completed",
        source_path=payload.get("source_path"),
        step_path=(payload.get("build") or {}).get("step_path"),
        warnings=payload.get("warnings", []),
        payload=payload,
        error_text=None,
    )
    schedule_job_webhook(job_id)
    return payload


def _finalize_future(job_id: str, future: Future[dict[str, Any]]) -> None:
    try:
        future.result()
    except CancelledError:
        update_job(
            job_id,
            status="cancelled",
            warnings=["Job was cancelled before the worker subprocess started."],
            payload={
                "failure": {
                    "stage": "queue",
                    "type": "cancelled",
                    "message": "Executor future cancelled.",
                    "hints": ["The job never left the thread-pool queue."],
                }
            },
            error_text="Executor future cancelled.",
        )
        schedule_job_webhook(job_id)
    except JobCancelledError as exc:
        update_job(
            job_id,
            status="cancelled",
            warnings=[str(exc)],
            payload={
                "failure": {
                    "stage": "worker",
                    "type": "cancelled",
                    "message": str(exc),
                    "hints": [
                        "The worker subprocess was terminated after a cancel request.",
                    ],
                }
            },
            error_text=str(exc),
        )
        schedule_job_webhook(job_id)
    except JobTimeoutError as exc:
        update_job(
            job_id,
            status="failed",
            warnings=[str(exc)],
            payload={
                "failure": {
                    "stage": "worker",
                    "type": "timeout",
                    "message": str(exc),
                    "hints": [
                        "Increase MESH2CAD_JOB_TIMEOUT_SEC or reduce mesh complexity / sample_count.",
                    ],
                }
            },
            error_text=str(exc),
        )
        schedule_job_webhook(job_id)
    except Exception as exc:
        update_job(
            job_id,
            status="failed",
            warnings=[str(exc)],
            payload={
                "failure": {
                    "stage": "worker",
                    "type": "error",
                    "message": str(exc),
                    "hints": [
                        "Inspect job artifacts (report) after completion, or re-run with --no-build.",
                        "If stderr mentions missing build123d, install optional dependency build123d.",
                    ],
                }
            },
            error_text=str(exc),
        )
        schedule_job_webhook(job_id)
    finally:
        with _FUTURES_LOCK:
            _FUTURES.pop(job_id, None)


def _clear_retry_artifacts(job_dir: Path) -> None:
    if not job_dir.exists():
        return
    for child in job_dir.iterdir():
        if child.name == CANCEL_FILENAME:
            child.unlink(missing_ok=True)
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
