from __future__ import annotations

import uuid
from pathlib import Path

from mesh2cad.api.schemas import JobCancelResponse, JobStatusResponse, ProcessMeshRequest, ProcessSubmitRequest
from mesh2cad.api.service import process_mesh
from mesh2cad.jobs.runner import request_job_cancel, submit_job
from mesh2cad.ui.db import create_job_with_id, get_job, get_job_paths
from mesh2cad.ui.routes import register_ui


def create_app():
    """Create an optional FastAPI app if FastAPI is installed."""
    try:
        from fastapi import FastAPI
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("FastAPI is not installed. Install it to use the HTTP API.") from exc

    app = FastAPI(title="ViminCADConverter API", version="0.1.0")
    register_ui(app)

    @app.post("/process")
    def process_endpoint(body: ProcessMeshRequest):
        return process_mesh(
            input_path=body.resolved_input_path(),
            output_dir=body.resolved_output_dir() if body.build else None,
            sample_count=body.sample_count,
            simplify_target_faces=body.simplify_target_faces,
            build=body.build,
            auto_tune_sampling=body.auto_tune_sampling,
            align_surface_metrics=body.align_surface_metrics,
            icp_iterations=body.icp_iterations,
            icp_seed=body.icp_seed,
        )

    @app.post("/process/submit")
    def process_submit(body: ProcessSubmitRequest):
        input_path = body.resolved_input_path()
        job_id = uuid.uuid4().hex
        _, job_dir = get_job_paths(job_id)
        create_job_with_id(
            job_id=job_id,
            user_id=0,
            original_name=input_path.name,
            input_path=input_path,
            output_dir=job_dir,
        )
        submit_job(
            job_id=job_id,
            input_path=input_path,
            output_dir=job_dir if body.build else None,
            artifact_dir=job_dir,
            sample_count=body.sample_count,
            simplify_target_faces=body.simplify_target_faces,
            build=body.build,
            auto_tune_sampling=body.auto_tune_sampling,
            align_surface_metrics=body.align_surface_metrics,
            icp_iterations=body.icp_iterations,
            icp_seed=body.icp_seed,
        )
        return {"job_id": job_id, "status": "queued"}

    @app.get("/process/jobs/{job_id}")
    def process_job_status(job_id: str):
        job = get_job(job_id)
        if job is None:
            return {"error": "Job not found."}
        return JobStatusResponse(
            job_id=job["id"],
            status=job["status"],
            warnings=job.get("warnings", []),
            payload=job.get("payload", {}),
            step_path=job.get("step_path"),
        ).model_dump()

    @app.post("/process/jobs/{job_id}/cancel", response_model=JobCancelResponse)
    def process_job_cancel(job_id: str):
        detail = request_job_cancel(job_id)
        message = (
            "Job removed from the queue before starting."
            if detail["status"] == "cancelled"
            else "Cancel requested; a running worker will stop when it observes the marker."
        )
        return JobCancelResponse(job_id=job_id, status=detail["status"], message=message)

    return app


def main() -> None:
    """Run the HTTP API with uvicorn if available."""
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("uvicorn is not installed. Install the API extras to run the server.") from exc

    uvicorn.run(create_app(), host="127.0.0.1", port=8000)
