"""Resolve downloadable artifact paths for v1 job API."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ARTIFACT_NAMES = frozenset({"report", "script", "step", "preview", "input"})

_SYNC_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def is_valid_sync_session_id(sync_id: str) -> bool:
    return bool(_SYNC_ID_RE.match(sync_id))


def job_view_from_process_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Shape the same keys ``resolve_artifact_path`` expects from a DB job row."""
    b = payload.get("build") or {}
    return {
        "step_path": b.get("step_path"),
        "source_path": payload.get("source_path"),
        "payload": payload,
    }


def write_session_artifacts(session_dir: Path, payload: dict[str, Any]) -> None:
    """Persist report + script under ``session_dir`` (same layout as async job dirs)."""
    session_dir.mkdir(parents=True, exist_ok=True)
    session_dir.joinpath("report.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    script = (payload.get("build") or {}).get("script")
    if script:
        session_dir.joinpath("reconstruction.py").write_text(str(script), encoding="utf-8")


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
