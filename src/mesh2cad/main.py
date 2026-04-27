from __future__ import annotations

import argparse
import json
from pathlib import Path

from mesh2cad.api.service import process_mesh

def main() -> None:
    """CLI entrypoint for local mesh processing."""
    parser = argparse.ArgumentParser(
        description="Run the ViminCADConverter (mesh2cad) pipeline on a mesh or point cloud."
    )
    parser.add_argument("input_path", type=Path, help="Path to the input mesh file.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory for outputs.")
    parser.add_argument("--sample-count", type=int, default=5_000, help="Surface sample count.")
    parser.add_argument(
        "--simplify-target-faces",
        type=int,
        default=None,
        help="Optional target face count before sampling.",
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Generate analysis and script only, without attempting CAD build/export.",
    )
    parser.add_argument(
        "--no-auto-tune",
        action="store_true",
        help="Use requested sample count as-is (no mesh-size clamping).",
    )
    parser.add_argument(
        "--no-align-surface-metrics",
        action="store_true",
        help="Skip ICP alignment for surface distance metrics in validation.",
    )
    parser.add_argument("--icp-iterations", type=int, default=10)
    parser.add_argument("--icp-seed", type=int, default=0)
    args = parser.parse_args()

    result = process_mesh(
        input_path=args.input_path,
        output_dir=args.output_dir,
        sample_count=args.sample_count,
        simplify_target_faces=args.simplify_target_faces,
        build=not args.no_build,
        auto_tune_sampling=not args.no_auto_tune,
        align_surface_metrics=not args.no_align_surface_metrics,
        icp_iterations=args.icp_iterations,
        icp_seed=args.icp_seed,
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
