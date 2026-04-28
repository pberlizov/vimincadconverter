"""RQ worker entry points (importable string paths for ``Queue.enqueue``)."""

from __future__ import annotations

from typing import Any


def rq_mesh_job_from_serializable(job: dict[str, Any]) -> dict[str, Any]:
    """RQ-friendly entry point that takes a single JSON-serializable dict."""
    return rq_mesh_job(**job)


def rq_mesh_job(
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
) -> dict[str, Any]:
    """Run the mesh job in an RQ worker (same subprocess worker as the thread pool)."""
    from mesh2cad.jobs.runner import complete_mesh_job_sync, finalize_mesh_job_failure

    try:
        return complete_mesh_job_sync(
            job_id=job_id,
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
            include_script=include_script,
            tolerances=tolerances,
            icp_hybrid_hull_weight=icp_hybrid_hull_weight,
        )
    except Exception as exc:
        finalize_mesh_job_failure(job_id, exc)
        raise
