"""Pydantic models for the versioned public HTTP API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TolerancesV1(BaseModel):
    linear: float = Field(default=0.25, gt=0)
    angular_deg: float = Field(default=2.0, gt=0)
    min_region_area: float = Field(default=5.0, gt=0)
    ransac_distance: float = Field(default=0.2, gt=0)


class ProcessMeshBodyV1(BaseModel):
    """Synchronous process request (JSON body). ``input_path`` must exist on the server."""

    input_path: Path
    output_dir: Path | None = None
    sample_count: int = Field(default=5_000, ge=100, le=200_000)
    simplify_target_faces: int | None = Field(default=None, ge=1, le=5_000_000)
    build: bool = True
    auto_tune_sampling: bool = True
    align_surface_metrics: bool = True
    icp_iterations: int = Field(default=10, ge=1, le=200)
    icp_seed: int = Field(default=0, ge=0, le=2_147_483_647)
    include_script: bool = True
    tolerances: TolerancesV1 | None = None
    icp_hybrid_hull_weight: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="ICP hull blend when auxiliary scan points exist; omit for pipeline default.",
    )

    @field_validator("input_path", "output_dir", mode="before")
    @classmethod
    def expand_path(cls, v: Any) -> Any:
        if v is None:
            return None
        return Path(v).expanduser()

    def resolved_input_path(self) -> Path:
        return self.input_path.expanduser().resolve()

    def resolved_output_dir(self) -> Path | None:
        if self.output_dir is None:
            return None
        return self.output_dir.expanduser().resolve()

    def tolerances_dict(self) -> dict[str, float] | None:
        if self.tolerances is None:
            return None
        return self.tolerances.model_dump()


class JobSubmitBodyV1(ProcessMeshBodyV1):
    """Async job: same as process body; ``input_path`` optional when uploading ``file`` instead."""

    input_path: Path | None = None
    webhook_url: str | None = Field(
        default=None,
        max_length=2048,
        description="HTTPS URL for POST on terminal job states (optional HMAC via MESH2CAD_WEBHOOK_SECRET).",
    )
