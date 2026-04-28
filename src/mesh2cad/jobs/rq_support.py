"""Optional Redis/RQ job queue (``MESH2CAD_JOB_BACKEND=rq``)."""

from __future__ import annotations

import os
from typing import Any

from mesh2cad.jobs.webhook_delivery import schedule_job_webhook
from mesh2cad.ui.db import update_job

_redis_client: Any | None = None


def use_rq_backend() -> bool:
    raw = os.environ.get("MESH2CAD_JOB_BACKEND", "").strip().lower()
    if raw in {"rq", "redis"}:
        return bool(os.environ.get("MESH2CAD_REDIS_URL", "").strip())
    return False


def _redis_connection():  # type: ignore[no-untyped-def]
    global _redis_client
    if _redis_client is None:
        from redis import Redis

        url = os.environ.get("MESH2CAD_REDIS_URL", "").strip()
        if not url:
            raise RuntimeError("MESH2CAD_REDIS_URL is required when MESH2CAD_JOB_BACKEND=rq.")
        _redis_client = Redis.from_url(url, decode_responses=False)
    return _redis_client


def ping_rq_redis() -> None:
    """Raise if Redis is unreachable (for readiness probes)."""
    _redis_connection().ping()


def reset_redis_connection_for_tests() -> None:
    """Clear cached Redis client (tests only)."""
    global _redis_client
    _redis_client = None


def rq_queue_name() -> str:
    return os.environ.get("MESH2CAD_RQ_QUEUE", "mesh2cad").strip() or "mesh2cad"


def _delete_existing_rq_job_if_any(job_id: str) -> None:
    """Remove a prior RQ job key so retries or fast replays can reuse ``job_id``."""
    try:
        from rq.exceptions import NoSuchJobError
        from rq.job import Job

        job = Job.fetch(job_id, connection=_redis_connection())
    except NoSuchJobError:
        return
    except Exception:
        return
    try:
        job.delete()
    except Exception:
        pass


def enqueue_mesh_job(
    *,
    job_id: str,
    input_path: str,
    output_dir: str | None,
    artifact_dir: str,
    sample_count: int,
    simplify_target_faces: int | None,
    build: bool,
    auto_tune_sampling: bool,
    align_surface_metrics: bool,
    icp_iterations: int,
    icp_seed: int,
    include_script: bool,
    tolerances: dict[str, Any] | None,
    icp_hybrid_hull_weight: float | None,
) -> None:
    """Enqueue ``mesh2cad.jobs.rq_tasks.rq_mesh_job`` with the same parameters as the thread runner."""
    from rq import Queue

    conn = _redis_connection()
    _delete_existing_rq_job_if_any(job_id)
    queue = Queue(rq_queue_name(), connection=conn)
    kwargs: dict[str, Any] = {
        "job_id": job_id,
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
    try:
        timeout_sec = int(os.environ.get("MESH2CAD_JOB_TIMEOUT_SEC", "900"))
    except ValueError:
        timeout_sec = 900
    queue.enqueue(
        "mesh2cad.jobs.rq_tasks.rq_mesh_job_from_serializable",
        args=(kwargs,),
        job_id=job_id,
        job_timeout=max(60, timeout_sec),
        result_ttl=0,
        failure_ttl=86_400,
    )


def try_cancel_rq_queued_job(job_id: str) -> bool:
    """Cancel an RQ job that has not started yet. Returns True if the job was cancelled in Redis."""
    if not use_rq_backend():
        return False
    try:
        from rq.exceptions import NoSuchJobError
        from rq.job import Job

        job = Job.fetch(job_id, connection=_redis_connection())
    except NoSuchJobError:
        return False
    except Exception:
        return False

    status = job.get_status()
    if status in {"queued", "deferred", "scheduled"}:
        job.cancel()
        update_job(
            job_id,
            status="cancelled",
            warnings=["Job was cancelled while waiting in the Redis queue."],
            payload={
                "failure": {
                    "stage": "queue",
                    "type": "cancelled",
                    "message": "RQ job cancelled before the worker started it.",
                    "hints": ["The job never reached a worker process."],
                }
            },
            error_text="RQ job cancelled.",
        )
        schedule_job_webhook(job_id)
        return True
    return False
