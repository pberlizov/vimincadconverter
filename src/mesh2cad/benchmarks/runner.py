from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from mesh2cad.benchmarks.cad_fixtures import two_hole_plate_script
from mesh2cad.cad.build123d_builder import build_step_from_script
from mesh2cad.domain.types import ToleranceConfig
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
    if generator == "build123d_two_hole_plate":
        scale = float(case.get("scale", 1.0))
        build_dir = tmp_dir / f"_{case['name']}_fixture_build"
        build_result = build_step_from_script(two_hole_plate_script(scale=scale), build_dir)
        if not build_result.success:
            raise RuntimeError(
                f"build123d fixture build failed for case {case['name']!r}: {build_result.errors}"
            )
        preview = build_result.metadata.get("preview_stl_path")
        if not isinstance(preview, str) or not preview:
            raise RuntimeError(f"build123d fixture missing preview STL for case {case['name']!r}")
        preview_path = Path(preview)
        if not preview_path.exists():
            raise RuntimeError(f"Preview STL does not exist: {preview_path}")
        dest = tmp_dir / f"{case['name']}.stl"
        dest.write_bytes(preview_path.read_bytes())
        return dest
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
    if generator == "build123d_two_hole_plate":
        raise ValueError("build123d_two_hole_plate is handled in _make_input_mesh_path, not _make_mesh.")
    raise ValueError(f"Unknown generator: {generator!r}")


def run_case(case: dict[str, Any], *, tmp_dir: Path, auto_tune: bool = False) -> PipelineResult:
    path = _make_input_mesh_path(case, tmp_dir)
    output_dir = None
    if case.get("build_export"):
        output_dir = tmp_dir / f"{case['name']}_cad"
    tolerances: ToleranceConfig | None = None
    raw_tol = case.get("tolerances")
    if isinstance(raw_tol, dict) and raw_tol:
        allowed = ("linear", "angular_deg", "min_region_area", "ransac_distance")
        kwargs = {k: raw_tol[k] for k in allowed if k in raw_tol}
        if kwargs:
            tolerances = ToleranceConfig(**kwargs)
    return run_pipeline(
        path,
        output_dir=output_dir,
        sample_count=int(case.get("sample_count", 3000)),
        auto_tune_sampling=auto_tune,
        tolerances=tolerances,
    )


def assert_case_expectations(case: dict[str, Any], result: PipelineResult) -> None:
    route = result.reconstruction_plan.route
    any_routes = case.get("expect_route_any_of")
    if isinstance(any_routes, list) and any_routes:
        assert route in any_routes, (case["name"], route, any_routes)
    elif "expect_route" in case:
        assert route == case["expect_route"]

    by_route = case.get("min_feature_kind_counts_by_route")
    if isinstance(by_route, dict) and by_route:
        counts = by_route.get(route)
        assert counts is not None, (case["name"], route, list(by_route))
        for kind, minimum in counts.items():
            assert result.feature_kinds.count(kind) >= int(minimum), (case["name"], kind, result.feature_kinds)
    else:
        min_counts: dict[str, int] = case.get("min_feature_kind_counts") or {}
        for kind, minimum in min_counts.items():
            assert result.feature_kinds.count(kind) >= int(minimum), (case["name"], kind, result.feature_kinds)
    min_prim: dict[str, int] = case.get("min_primitive_kind_counts") or {}
    for kind, minimum in min_prim.items():
        assert result.primitive_kinds.count(kind) >= int(minimum), (case["name"], kind, result.primitive_kinds)
    if case.get("build_export"):
        assert result.build is not None, case["name"]
        assert result.build.build_success, (case["name"], result.build.warnings if result.build else [])

    substr = case.get("expect_warning_substr")
    if substr:
        assert any(substr in w for w in result.warnings), (case["name"], result.warnings)
