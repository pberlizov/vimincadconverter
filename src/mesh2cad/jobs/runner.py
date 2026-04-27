from __future__ import annotations

from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Any

from mesh2cad.jobs.exceptions import CANCEL_FILENAME, JobCancelledError, JobTimeoutError
from mesh2cad.jobs.worker_subprocess import run_cli_worker_subprocess
from mesh2cad.ui.db import get_job_paths, update_job

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
    return {"status": "cancel_requested", "detail": "marker_written"}


def get_job_future(job_id: str) -> Future[dict[str, Any]] | None:
    with _FUTURES_LOCK:
        return _FUTURES.get(job_id)


def _executor() -> ThreadPoolExecutor:
    global _EXECUTOR
    with _EXECUTOR_LOCK:
        if _EXECUTOR is None:
            _EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mesh2cad-job")
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
) -> dict[str, Any]:
    update_job(job_id, status="processing")
    payload = run_cli_worker_subprocess(
        input_path=input_path,
        output_dir=output_dir,
        artifact_dir=artifact_dir,
        sample_count=sample_count,
        simplify_target_faces=simplify_target_faces,
        build=build,
        auto_tune_sampling=auto_tune_sampling,
        align_surface_metrics=align_surface_metrics,
        icp_iterations=icp_iterations,
        icp_seed=icp_seed,
    )
    update_job(
        job_id,
        status="completed",
        source_path=payload.get("source_path"),
        step_path=(payload.get("build") or {}).get("step_path"),
        warnings=payload.get("warnings", []),
        payload=payload,
        error_text=None,
    )
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
    finally:
        with _FUTURES_LOCK:
            _FUTURES.pop(job_id, None)
