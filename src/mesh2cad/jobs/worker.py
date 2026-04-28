from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from mesh2cad.api.service import process_mesh
from mesh2cad.api.v1.artifacts import write_session_artifacts
from mesh2cad.domain.types import ToleranceConfig


def run_worker(
    *,
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
) -> dict[str, Any]:
    tc: ToleranceConfig | None = None
    if isinstance(tolerances, dict) and tolerances:
        merged = {**asdict(ToleranceConfig()), **tolerances}
        tc = ToleranceConfig(
            linear=float(merged["linear"]),
            angular_deg=float(merged["angular_deg"]),
            min_region_area=float(merged["min_region_area"]),
            ransac_distance=float(merged["ransac_distance"]),
        )
    payload = process_mesh(
        input_path=input_path,
        output_dir=output_dir,
        sample_count=sample_count,
        simplify_target_faces=simplify_target_faces,
        build=build,
        tolerances=tc,
        auto_tune_sampling=auto_tune_sampling,
        align_surface_metrics=align_surface_metrics,
        icp_iterations=icp_iterations,
        icp_seed=icp_seed,
        include_script=include_script,
        icp_hybrid_hull_weight=icp_hybrid_hull_weight,
    )
    write_session_artifacts(Path(artifact_dir), payload)
    return payload


def run_worker_from_request(data: dict[str, Any]) -> dict[str, Any]:
    """Dispatch ``run_worker`` from a JSON request dict (see ``worker_request.json``)."""
    simplify = data.get("simplify_target_faces")
    hybrid = data.get("icp_hybrid_hull_weight")
    return run_worker(
        input_path=data["input_path"],
        output_dir=data.get("output_dir"),
        artifact_dir=data["artifact_dir"],
        sample_count=int(data.get("sample_count", 5000)),
        simplify_target_faces=int(simplify) if simplify is not None else None,
        build=bool(data.get("build", True)),
        auto_tune_sampling=bool(data.get("auto_tune_sampling", True)),
        align_surface_metrics=bool(data.get("align_surface_metrics", True)),
        icp_iterations=int(data.get("icp_iterations", 10)),
        icp_seed=int(data.get("icp_seed", 0)),
        include_script=bool(data.get("include_script", True)),
        tolerances=data.get("tolerances") if isinstance(data.get("tolerances"), dict) else None,
        icp_hybrid_hull_weight=float(hybrid) if hybrid is not None else None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a ViminCADConverter (mesh2cad) job worker subprocess."
    )
    parser.add_argument(
        "--worker-request-json",
        type=Path,
        required=True,
        help="Path to worker_request.json (written by the job runner).",
    )
    args = parser.parse_args()
    data = json.loads(Path(args.worker_request_json).read_text(encoding="utf-8"))
    payload = run_worker_from_request(data)
    print(json.dumps(payload, default=str))


if __name__ == "__main__":
    main()
