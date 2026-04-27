from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from mesh2cad.pipeline.orchestrator import PipelineResult, run_pipeline


def default_cases_path() -> Path:
    # runner.py -> mesh2cad/benchmarks -> mesh2cad -> src -> repo root
    return Path(__file__).resolve().parents[3] / "benchmarks" / "cases.json"


def load_cases(path: Path | None = None) -> list[dict[str, Any]]:
    catalog = path or default_cases_path()
    raw = json.loads(catalog.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Benchmark catalog must be a JSON array.")
    return raw


def _make_input_mesh_path(case: dict[str, Any], tmp_dir: Path) -> Path:
    """Return a path on disk for ``run_pipeline`` (triangle mesh or point cloud)."""
    generator = case["generator"]
    if generator == "point_cloud_box":
        extents = tuple(float(x) for x in case["extents"])
        mesh = trimesh.creation.box(extents=extents)
        n = int(case.get("point_count", 5000))
        pts, _ = trimesh.sample.sample_surface(mesh, n)
        pts = np.asarray(pts, dtype=np.float64)
        noise = float(case.get("point_noise_std", 0.0))
        if noise > 0.0:
            seed = int(case.get("noise_seed", 0)) & 0xFFFF_FFFF
            rng = np.random.default_rng(seed)
            pts = pts + rng.normal(0.0, noise, size=pts.shape)
        path = tmp_dir / f"{case['name']}.xyz"
        np.savetxt(path, pts, fmt="%.6f")
        return path
    mesh = _make_mesh(case)
    path = tmp_dir / f"{case['name']}.stl"
    mesh.export(path)
    return path


def _make_mesh(case: dict[str, Any]) -> trimesh.Trimesh:
    generator = case["generator"]
    if generator == "box":
        extents = tuple(float(x) for x in case["extents"])
        return trimesh.creation.box(extents=extents)
    if generator == "cylinder":
        return trimesh.creation.cylinder(
            radius=float(case["radius"]),
            height=float(case["height"]),
            sections=int(case.get("sections", 64)),
        )
    if generator == "capsule":
        return trimesh.creation.capsule(
            height=float(case["height"]),
            radius=float(case["radius"]),
            count=[
                int(case.get("count_a", 16)),
                int(case.get("count_b", 16)),
            ],
        )
    if generator == "icosphere":
        return trimesh.creation.icosphere(
            subdivisions=int(case.get("subdivisions", 2)),
            radius=float(case["radius"]),
        )
    raise ValueError(f"Unknown generator: {generator!r}")


def run_case(case: dict[str, Any], *, tmp_dir: Path, auto_tune: bool = False) -> PipelineResult:
    path = _make_input_mesh_path(case, tmp_dir)
    output_dir = None
    if case.get("build_export"):
        output_dir = tmp_dir / f"{case['name']}_cad"
    return run_pipeline(
        path,
        output_dir=output_dir,
        sample_count=int(case.get("sample_count", 3000)),
        auto_tune_sampling=auto_tune,
    )


def assert_case_expectations(case: dict[str, Any], result: PipelineResult) -> None:
    if "expect_route" in case:
        assert result.reconstruction_plan.route == case["expect_route"]
    min_counts: dict[str, int] = case.get("min_feature_kind_counts") or {}
    for kind, minimum in min_counts.items():
        assert result.feature_kinds.count(kind) >= int(minimum), (case["name"], kind, result.feature_kinds)
    if case.get("build_export"):
        assert result.build is not None, case["name"]
        assert result.build.build_success, (case["name"], result.build.warnings if result.build else [])

    substr = case.get("expect_warning_substr")
    if substr:
        assert any(substr in w for w in result.warnings), (case["name"], result.warnings)
