from __future__ import annotations

import argparse
import json
from pathlib import Path

from mesh2cad.api.service import process_mesh


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
) -> dict:
    payload = process_mesh(
        input_path=input_path,
        output_dir=output_dir,
        sample_count=sample_count,
        simplify_target_faces=simplify_target_faces,
        build=build,
        auto_tune_sampling=auto_tune_sampling,
        align_surface_metrics=align_surface_metrics,
        icp_iterations=icp_iterations,
        icp_seed=icp_seed,
    )
    _write_job_artifacts(Path(artifact_dir), payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a ViminCADConverter (mesh2cad) job worker subprocess."
    )
    parser.add_argument("--input-path", required=True)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--sample-count", type=int, default=5_000)
    parser.add_argument("--simplify-target-faces", type=int, default=None)
    parser.add_argument("--build", action="store_true")
    parser.add_argument(
        "--no-auto-tune",
        action="store_true",
        help="Disable mesh-size-based sample count clamping.",
    )
    parser.add_argument(
        "--no-align-surface-metrics",
        action="store_true",
        help="Skip ICP alignment for surface RMS/max distance in validation.",
    )
    parser.add_argument("--icp-iterations", type=int, default=10)
    parser.add_argument("--icp-seed", type=int, default=0)
    args = parser.parse_args()

    payload = run_worker(
        input_path=args.input_path,
        output_dir=args.output_dir,
        artifact_dir=args.artifact_dir,
        sample_count=args.sample_count,
        simplify_target_faces=args.simplify_target_faces,
        build=args.build,
        auto_tune_sampling=not args.no_auto_tune,
        align_surface_metrics=not args.no_align_surface_metrics,
        icp_iterations=args.icp_iterations,
        icp_seed=args.icp_seed,
    )
    print(json.dumps(payload, default=str))


def _write_job_artifacts(job_dir: Path, payload: dict) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    job_dir.joinpath("report.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    script = (payload.get("build") or {}).get("script")
    if script:
        job_dir.joinpath("reconstruction.py").write_text(str(script), encoding="utf-8")


if __name__ == "__main__":
    main()
