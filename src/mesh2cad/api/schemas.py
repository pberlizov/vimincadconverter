from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ProcessMeshRequest(BaseModel):
    input_path: Path
    output_dir: Path | None = None
    sample_count: int = Field(default=5_000, ge=100, le=200_000)
    simplify_target_faces: int | None = Field(default=None, ge=1, le=5_000_000)
    build: bool = True
    auto_tune_sampling: bool = True
    align_surface_metrics: bool = True
    icp_iterations: int = Field(default=10, ge=1, le=200)
    icp_seed: int = Field(default=0, ge=0, le=2_147_483_647)

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


class ProcessSubmitRequest(ProcessMeshRequest):
    """Same fields as sync /process; used for async job submission."""

    pass


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    warnings: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    step_path: str | None = None


class JobCancelResponse(BaseModel):
    job_id: str
    status: str
    message: str
