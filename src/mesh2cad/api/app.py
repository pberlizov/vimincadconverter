from __future__ import annotations

import os
import uuid
from pathlib import Path

from mesh2cad.api.middleware_request_id import RequestIDMiddleware
from mesh2cad.api.schemas import (
    JobCancelResponse,
    JobRetryResponse,
    JobStatusResponse,
    ProcessMeshRequest,
    ProcessSubmitRequest,
)
from mesh2cad.api.service import process_mesh
from mesh2cad.api.v1.router import health_router, router as v1_router
from mesh2cad.domain.types import ToleranceConfig
from mesh2cad.jobs.runner import request_job_cancel, retry_job, submit_job
from mesh2cad.ui.db import create_job_with_id, get_job, get_job_paths
from mesh2cad.ui.routes import register_ui


def create_app():
    """Create an optional FastAPI app if FastAPI is not installed."""
    try:
        from fastapi import FastAPI, HTTPException
        from starlette.middleware.cors import CORSMiddleware
        from starlette.responses import PlainTextResponse
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("FastAPI is not installed. Install it to use the HTTP API.") from exc

    from mesh2cad.observability.access_middleware import AccessLogMiddleware
    from mesh2cad.observability.logging_config import configure_logging
    from mesh2cad.observability.metrics import prometheus_text
    from mesh2cad.security.body_limit import BodySizeLimitMiddleware
    from mesh2cad.security.rate_limit import RateLimitMiddleware
    from mesh2cad.security.webhook_url import WebhookUrlRejected, validate_webhook_url

    configure_logging()

    app = FastAPI(
        title="ViminCADConverter API",
        version="1.0.0",
        description=(
            "Mesh and point-cloud analysis with optional build123d export. "
            "Use **/v1/** routes for uploads, API keys, artifact downloads, and webhooks. "
            "Legacy **/process** routes remain for backward compatibility."
        ),
    )
    cors = os.environ.get("MESH2CAD_CORS_ORIGINS", "").strip()
    if cors:
        origins = [o.strip() for o in cors.split(",") if o.strip()]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(BodySizeLimitMiddleware)

    register_ui(app)
    app.include_router(health_router())
    app.include_router(v1_router)

    if os.environ.get("MESH2CAD_METRICS_ENABLED", "").lower() in {"1", "true", "yes", "on"}:

        @app.get("/metrics")
        def prometheus_metrics():
            return PlainTextResponse(prometheus_text(), media_type="text/plain; version=0.0.4")

    @app.post("/process")
    def process_endpoint(body: ProcessMeshRequest):
        tc = (
            ToleranceConfig(**body.tolerances.model_dump())
            if body.tolerances is not None
            else None
        )
        return process_mesh(
            input_path=body.resolved_input_path(),
            output_dir=body.resolved_output_dir() if body.build else None,
            sample_count=body.sample_count,
            simplify_target_faces=body.simplify_target_faces,
            build=body.build,
            tolerances=tc,
            auto_tune_sampling=body.auto_tune_sampling,
            align_surface_metrics=body.align_surface_metrics,
            icp_iterations=body.icp_iterations,
            icp_seed=body.icp_seed,
            include_script=body.include_script,
            icp_hybrid_hull_weight=body.icp_hybrid_hull_weight,
        )

    @app.post("/process/submit")
    def process_submit(body: ProcessSubmitRequest):
        try:
            validate_webhook_url(body.webhook_url)
        except WebhookUrlRejected as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        input_path = body.resolved_input_path()
        job_id = uuid.uuid4().hex
        _, job_dir = get_job_paths(job_id)
        request_payload = body.model_dump(mode="json")
        create_job_with_id(
            job_id=job_id,
            user_id=0,
            original_name=input_path.name,
            input_path=input_path,
            output_dir=job_dir,
            request_payload=request_payload,
        )
        tc_dict = body.tolerances.model_dump() if body.tolerances is not None else None
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
            include_script=body.include_script,
            tolerances=tc_dict,
            icp_hybrid_hull_weight=body.icp_hybrid_hull_weight,
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

    @app.post("/process/jobs/{job_id}/retry", response_model=JobRetryResponse)
    def process_job_retry(job_id: str):
        detail = retry_job(job_id)
        if detail["status"] == "not_found":
            return JobRetryResponse(job_id=job_id, status="not_found", message="Job not found.")
        if detail["status"] == "invalid_state":
            return JobRetryResponse(
                job_id=job_id,
                status="invalid_state",
                message="Only completed, failed, or cancelled jobs can be retried.",
            )
        if detail["status"] == "missing_request":
            return JobRetryResponse(
                job_id=job_id,
                status="missing_request",
                message="The original request parameters were not stored for this job.",
            )
        return JobRetryResponse(job_id=job_id, status="queued", message="Retry submitted.")

    return app


def main() -> None:
    """Run the HTTP API with uvicorn if available."""
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("uvicorn is not installed. Install the API extras to run the server.") from exc

    uvicorn.run(create_app(), host="127.0.0.1", port=8000)
