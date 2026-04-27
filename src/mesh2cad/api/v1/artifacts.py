"""Resolve downloadable artifact paths for v1 job API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

ARTIFACT_NAMES = frozenset({"report", "script", "step", "preview", "input"})


def resolve_artifact_path(job: dict[str, Any], job_dir: Path, artifact_name: str) -> Path | None:
    if artifact_name not in ARTIFACT_NAMES:
        return None
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


def artifact_media_type(name: str) -> str:
    if name == "report":
        return "application/json"
    if name == "script":
        return "text/x-python"
    if name in {"step", "preview", "input"}:
        return "application/octet-stream"
    return "application/octet-stream"


def artifact_filename(name: str, job: dict[str, Any]) -> str:
    if name == "input" and job.get("source_path"):
        return Path(str(job["source_path"])).name
    if name == "step":
        sp = job.get("step_path")
        if isinstance(sp, str) and sp:
            return Path(sp).name
        return "model.step"
    if name == "preview":
        return "preview.stl"
    return f"{name}.bin"
