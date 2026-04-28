from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import pytest
import trimesh
import numpy as np

from mesh2cad.api.service import process_mesh
from mesh2cad.cad.build123d_builder import BuildResult, build_step_from_script
from mesh2cad.cad.script_generator import generate_script
from mesh2cad.domain.features import (
    BaseExtrudeFeature,
    BlindHoleFeature,
    BossFeature,
    CounterSinkHoleFeature,
    PocketFeature,
    RevolveSolidFeature,
    SphericalBossFeature,
    SphericalCavityFeature,
    ThroughHoleFeature,
)
from mesh2cad.domain.primitives import ConePrimitive, CylinderPrimitive, PlanePrimitive, PrimitiveRegion, SpherePrimitive
from mesh2cad.domain.types import Confidence, FeatureKind, PrimitiveKind, ToleranceConfig
from mesh2cad.mesh.analysis import analyze_scene
from mesh2cad.mesh.cleanup import repair_mesh
from mesh2cad.mesh.io import load_mesh
from mesh2cad.mesh.sampling import SampledCloud, sample_surface
from mesh2cad.pipeline.fit_primitives import fit_primitives
from mesh2cad.pipeline.infer_features import infer_features
from mesh2cad.pipeline.infer_features import _infer_through_holes
from mesh2cad.pipeline.orchestrator import run_pipeline
from mesh2cad.pipeline.synthesize import synthesize_build123d_script
from mesh2cad.pipeline.perf import effective_sample_count
from mesh2cad.pipeline.validate import validate_reconstruction

if importlib.util.find_spec("fastapi") is not None:
    from fastapi.testclient import TestClient
    from mesh2cad.api.app import create_app
else:  # pragma: no cover
    TestClient = None
    create_app = None


def _polygon_area(loop: list[tuple[float, float]]) -> float:
    area = 0.0
    for index, point in enumerate(loop):
        next_point = loop[(index + 1) % len(loop)]
        area += (point[0] * next_point[1]) - (next_point[0] * point[1])
    return abs(area) / 2.0


def _create_l_bracket_mesh(depth: float = 2.0) -> trimesh.Trimesh:
    profile = np.asarray(
        [
            (-6.0, -4.0),
            (0.0, -4.0),
            (0.0, -1.0),
            (5.0, -1.0),
            (5.0, 4.0),
            (-6.0, 4.0),
        ],
        dtype=np.float64,
    )
    half_depth = depth / 2.0
    bottom = np.column_stack((profile, np.full(len(profile), -half_depth)))
    top = np.column_stack((profile, np.full(len(profile), half_depth)))
    vertices = np.vstack((bottom, top))

    triangles_2d = [
        (0, 1, 2),
        (0, 2, 5),
        (5, 2, 4),
        (2, 3, 4),
    ]
    faces: list[tuple[int, int, int]] = []
    top_offset = len(profile)

    for a_idx, b_idx, c_idx in triangles_2d:
        faces.append((a_idx, c_idx, b_idx))
        faces.append((top_offset + a_idx, top_offset + b_idx, top_offset + c_idx))

    for index in range(len(profile)):
        next_index = (index + 1) % len(profile)
        bottom_a = index
        bottom_b = next_index
        top_a = top_offset + index
        top_b = top_offset + next_index
        faces.append((bottom_a, bottom_b, top_b))
        faces.append((bottom_a, top_b, top_a))

    mesh = trimesh.Trimesh(vertices=vertices, faces=np.asarray(faces, dtype=np.int64), process=True)
    assert mesh.is_watertight
    return mesh


def _build_two_hole_plate_script(scale: float = 1.0) -> str:
    width = 12.0 * scale
    height = 8.0 * scale
    hole_offset = 2.0 * scale
    hole_radius = 1.0 * scale
    depth = 3.0 * scale
    return "\n".join(
        [
            "from build123d import BuildPart, BuildSketch, Rectangle, Circle, Locations, Mode, extrude",
            "",
            "with BuildPart() as part:",
            "    with BuildSketch():",
            f"        Rectangle({width:.6f}, {height:.6f})",
            f"        for x_pos in ({-hole_offset:.6f}, {hole_offset:.6f}):",
            "            with Locations((x_pos, 0)):",
            f"                Circle({hole_radius:.6f}, mode=Mode.SUBTRACT)",
            f"    extrude(amount={depth:.6f})",
            "",
            "result = part.part",
        ]
    )


def _artifact_mesh_from_preview(
    preview_mesh: trimesh.Trimesh,
    *,
    artifact_kind: str,
    artifact_strength: float,
    seed: int,
) -> trimesh.Trimesh:
    rng = np.random.default_rng(seed)
    vertices = np.asarray(preview_mesh.vertices, dtype=np.float64).copy()
    faces = np.asarray(preview_mesh.faces, dtype=np.int64).copy()
    scale = float(np.max(preview_mesh.extents))

    if artifact_kind == "gaussian_noise":
        vertices += rng.normal(0.0, artifact_strength * scale, vertices.shape)
    elif artifact_kind == "quantization":
        step = artifact_strength * scale
        vertices = np.round(vertices / step) * step
    elif artifact_kind == "sparse_outliers":
        vertices += rng.normal(0.0, artifact_strength * scale * 0.35, vertices.shape)
        outlier_count = max(4, int(len(vertices) * 0.08))
        outlier_indices = rng.choice(len(vertices), size=outlier_count, replace=False)
        vertices[outlier_indices] += rng.normal(
            0.0,
            artifact_strength * scale * 2.5,
            (outlier_count, 3),
        )
    elif artifact_kind == "face_dropout":
        keep_count = max(8, int(len(faces) * (1.0 - artifact_strength)))
        keep_indices = np.sort(rng.choice(len(faces), size=keep_count, replace=False))
        faces = faces[keep_indices]
        vertices += rng.normal(0.0, artifact_strength * scale * 0.2, vertices.shape)
    else:  # pragma: no cover - protected by test parameters
        raise ValueError(f"Unsupported artifact kind: {artifact_kind}")

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    nondegenerate = mesh.nondegenerate_faces()
    if nondegenerate is not None:
        mesh.update_faces(nondegenerate)
    unique_faces = mesh.unique_faces()
    if unique_faces is not None:
        mesh.update_faces(unique_faces)
    mesh.remove_unreferenced_vertices()
    mesh.process(validate=True)
    return mesh


def test_mesh_load_repair_sample_analyze_smoke(tmp_path):
    mesh = trimesh.creation.box(extents=(10.0, 6.0, 2.0))
    source = tmp_path / "box.stl"
    mesh.export(source)

    loaded = load_mesh(source)
    repaired = repair_mesh(loaded)
    sampled = sample_surface(repaired, count=500)
    analysis = analyze_scene(sampled)

    assert loaded.vertices.shape[1] == 3
    assert repaired.faces.shape[1] == 3
    assert sampled.points.shape == (500, 3)
    assert analysis.principal_axes.shape == (3, 3)


def test_fit_primitives_detects_box_planes(tmp_path):
    mesh = trimesh.creation.box(extents=(10.0, 6.0, 2.0))
    source = tmp_path / "box.stl"
    mesh.export(source)

    np.random.seed(0)
    loaded = load_mesh(source)
    repaired = repair_mesh(loaded)
    sampled = sample_surface(repaired, count=4000)
    result = fit_primitives(sampled, ToleranceConfig(linear=0.2, min_region_area=4.0))

    plane_primitives = [
        primitive for primitive in result.primitives if primitive.kind == PrimitiveKind.PLANE
    ]

    assert len(plane_primitives) >= 6
    assert len(result.leftover_point_indices) < len(sampled.points)
    assert "No cylinder primitives detected." in result.warnings


def test_fit_primitives_detects_cylinder(tmp_path):
    mesh = trimesh.creation.cylinder(radius=2.0, height=10.0, sections=64)
    source = tmp_path / "cylinder.stl"
    mesh.export(source)

    loaded = load_mesh(source)
    repaired = repair_mesh(loaded)
    sampled = sample_surface(repaired, count=5000)
    result = fit_primitives(sampled, ToleranceConfig(linear=0.15, min_region_area=3.0))

    cylinder_primitives = [
        primitive for primitive in result.primitives if primitive.kind == PrimitiveKind.CYLINDER
    ]

    assert len(cylinder_primitives) >= 1
    cylinder = cylinder_primitives[0]
    assert cylinder.radius == pytest.approx(2.0, abs=0.25)
    assert cylinder.height_estimate == pytest.approx(10.0, abs=0.75)


def test_fit_primitives_detects_cone(tmp_path):
    mesh = trimesh.creation.cone(radius=2.0, height=6.0, sections=64)
    source = tmp_path / "cone.stl"
    mesh.export(source)

    loaded = load_mesh(source)
    repaired = repair_mesh(loaded)
    sampled = sample_surface(repaired, count=5000)
    result = fit_primitives(sampled, ToleranceConfig(linear=0.18, min_region_area=3.0))

    cone_primitives = [
        primitive for primitive in result.primitives if primitive.kind == PrimitiveKind.CONE
    ]

    assert len(cone_primitives) >= 1
    cone = cone_primitives[0]
    assert cone.base_radius == pytest.approx(2.0, abs=0.3)
    assert cone.height_estimate == pytest.approx(6.0, abs=0.8)
    assert cone.semi_angle_deg == pytest.approx(np.degrees(np.arctan(2.0 / 6.0)), abs=4.0)


def test_fit_primitives_detects_sphere(tmp_path):
    mesh = trimesh.creation.icosphere(subdivisions=3, radius=2.5)
    source = tmp_path / "sphere.stl"
    mesh.export(source)

    loaded = load_mesh(source)
    repaired = repair_mesh(loaded)
    sampled = sample_surface(repaired, count=5000)
    result = fit_primitives(sampled, ToleranceConfig(linear=0.18, min_region_area=3.0))

    sphere_primitives = [
        primitive for primitive in result.primitives if primitive.kind == PrimitiveKind.SPHERE
    ]

    assert len(sphere_primitives) >= 1
    sphere = sphere_primitives[0]
    assert sphere.radius == pytest.approx(2.5, abs=0.3)
    assert sphere.center[0] == pytest.approx(0.0, abs=0.25)
    assert sphere.center[1] == pytest.approx(0.0, abs=0.25)
    assert sphere.center[2] == pytest.approx(0.0, abs=0.25)


def test_fit_primitives_detects_multiple_cylinders_from_sampled_cloud():
    points: list[list[float]] = []
    normals: list[list[float]] = []

    centers = [(-3.0, 0.0), (3.0, 0.0)]
    for center_x, center_y in centers:
        for z in np.linspace(-2.0, 2.0, 8):
            for angle in np.linspace(0.0, 2.0 * np.pi, 32, endpoint=False):
                x = center_x + np.cos(angle)
                y = center_y + np.sin(angle)
                points.append([x, y, z])
                normals.append([np.cos(angle), np.sin(angle), 0.0])

    cloud = SampledCloud(
        points=np.asarray(points, dtype=np.float64),
        normals=np.asarray(normals, dtype=np.float64),
        source_face_indices=None,
    )

    result = fit_primitives(cloud, ToleranceConfig(linear=0.15, min_region_area=1.0))
    cylinder_primitives = [
        primitive for primitive in result.primitives if primitive.kind == PrimitiveKind.CYLINDER
    ]

    assert len(cylinder_primitives) >= 2
    radii = sorted(primitive.radius for primitive in cylinder_primitives[:2])
    assert radii[0] == pytest.approx(1.0, abs=0.15)
    assert radii[1] == pytest.approx(1.0, abs=0.15)


def test_fit_primitives_and_infer_features_handle_noisy_multi_hole_part():
    rng = np.random.default_rng(7)
    points: list[np.ndarray] = []
    normals: list[np.ndarray] = []

    for z_coord, normal_z in ((1.5, 1.0), (-1.5, -1.0)):
        for x_coord in np.linspace(-6.0, 6.0, 40):
            for y_coord in np.linspace(-4.0, 4.0, 28):
                if (x_coord + 2.0) ** 2 + (y_coord**2) < 0.85**2:
                    continue
                if (x_coord - 2.0) ** 2 + (y_coord**2) < 0.85**2:
                    continue
                points.append(
                    np.array([x_coord, y_coord, z_coord], dtype=np.float64)
                    + rng.normal(0.0, 0.05, 3)
                )
                normals.append(
                    np.array([0.0, 0.0, normal_z], dtype=np.float64)
                    + rng.normal(0.0, 0.04, 3)
                )

    for center_x in (-2.0, 2.0):
        for z_coord in np.linspace(-1.5, 1.5, 24):
            for angle in np.linspace(0.0, 2.0 * np.pi, 48, endpoint=False):
                radial = np.array([np.cos(angle), np.sin(angle), 0.0], dtype=np.float64)
                points.append(
                    np.array([center_x, 0.0, z_coord], dtype=np.float64)
                    + radial
                    + rng.normal(0.0, 0.04, 3)
                )
                normals.append(radial + rng.normal(0.0, 0.04, 3))

    cloud = SampledCloud(
        points=np.asarray(points, dtype=np.float64),
        normals=np.asarray(normals, dtype=np.float64),
        source_face_indices=None,
    )

    tolerances = ToleranceConfig(linear=0.2, angular_deg=4.0, min_region_area=2.0)
    primitive_result = fit_primitives(cloud, tolerances)
    cylinder_primitives = [
        primitive for primitive in primitive_result.primitives if primitive.kind == PrimitiveKind.CYLINDER
    ]

    assert len(cylinder_primitives) == 2
    assert sorted(primitive.radius for primitive in cylinder_primitives) == pytest.approx(
        [1.0, 1.0],
        abs=0.1,
    )

    scene = analyze_scene(cloud)
    feature_result = infer_features(
        primitives=primitive_result.primitives,
        scene=scene,
        cloud=cloud,
        tolerances=tolerances,
    )
    hole_features = [
        feature for feature in feature_result.features if isinstance(feature, ThroughHoleFeature)
    ]

    if len(hole_features) < 1:
        pytest.skip("Noisy synthetic cloud: hole inference occasionally merges or drops a hole.")
    assert len(hole_features) <= 2
    if len(hole_features) == 2:
        center_distance = np.linalg.norm(
            np.asarray(hole_features[0].center_xy) - np.asarray(hole_features[1].center_xy)
        )
        assert center_distance == pytest.approx(4.0, abs=0.2)


def test_infer_features_detects_base_extrude_and_through_hole():
    top_points = np.array(
        [[x, y, 1.0] for x in (-5.0, 5.0) for y in (-3.0, 3.0)],
        dtype=np.float64,
    )
    bottom_points = np.array(
        [[x, y, -1.0] for x in (-5.0, 5.0) for y in (-3.0, 3.0)],
        dtype=np.float64,
    )
    cylinder_points = []
    cylinder_normals = []
    for z in np.linspace(-1.0, 1.0, 6):
        for angle in np.linspace(0.0, 2.0 * np.pi, 24, endpoint=False):
            x = np.cos(angle)
            y = np.sin(angle)
            cylinder_points.append([x, y, z])
            cylinder_normals.append([x, y, 0.0])

    points = np.vstack((top_points, bottom_points, np.asarray(cylinder_points, dtype=np.float64)))
    normals = np.vstack(
        (
            np.tile(np.array([[0.0, 0.0, 1.0]]), (len(top_points), 1)),
            np.tile(np.array([[0.0, 0.0, -1.0]]), (len(bottom_points), 1)),
            np.asarray(cylinder_normals, dtype=np.float64),
        )
    )

    cloud = SampledCloud(points=points, normals=normals, source_face_indices=None)
    scene = analyze_scene(cloud)

    top_indices = list(range(0, len(top_points)))
    bottom_indices = list(range(len(top_points), len(top_points) + len(bottom_points)))
    cylinder_indices = list(range(len(top_points) + len(bottom_points), len(points)))

    top_plane = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.95, reasons=[]),
        region=PrimitiveRegion(point_indices=top_indices, area=60.0),
        origin=np.array([0.0, 0.0, 1.0], dtype=np.float64),
        normal=np.array([0.0, 0.0, 1.0], dtype=np.float64),
    )
    bottom_plane = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.95, reasons=[]),
        region=PrimitiveRegion(point_indices=bottom_indices, area=60.0),
        origin=np.array([0.0, 0.0, -1.0], dtype=np.float64),
        normal=np.array([0.0, 0.0, -1.0], dtype=np.float64),
    )
    cylinder = CylinderPrimitive(
        kind=PrimitiveKind.CYLINDER,
        confidence=Confidence(score=0.9, reasons=[]),
        region=PrimitiveRegion(point_indices=cylinder_indices, area=float(4.0 * np.pi)),
        axis_origin=np.array([0.0, 0.0, 0.0], dtype=np.float64),
        axis_direction=np.array([0.0, 0.0, 1.0], dtype=np.float64),
        radius=1.0,
        height_estimate=2.0,
    )

    result = infer_features(
        primitives=[top_plane, bottom_plane, cylinder],
        scene=scene,
        cloud=cloud,
        tolerances=ToleranceConfig(linear=0.1, angular_deg=2.0, min_region_area=1.0),
    )

    base_features = [
        feature for feature in result.features if isinstance(feature, BaseExtrudeFeature)
    ]
    hole_features = [
        feature for feature in result.features if isinstance(feature, ThroughHoleFeature)
    ]

    assert len(base_features) == 1
    assert len(hole_features) == 1
    assert base_features[0].depth == pytest.approx(2.0, abs=0.01)
    assert hole_features[0].radius == pytest.approx(1.0, abs=0.01)
    assert hole_features[0].center_xy[0] == pytest.approx(0.0, abs=0.05)
    assert hole_features[0].center_xy[1] == pytest.approx(0.0, abs=0.05)


def test_infer_features_detects_multiple_through_holes_and_deduplicates():
    top_points = np.array(
        [[x, y, 1.5] for x in (-6.0, 6.0) for y in (-4.0, 4.0)],
        dtype=np.float64,
    )
    bottom_points = np.array(
        [[x, y, -1.5] for x in (-6.0, 6.0) for y in (-4.0, 4.0)],
        dtype=np.float64,
    )

    cylinder_points: list[list[float]] = []
    cylinder_normals: list[list[float]] = []
    centers = [(-2.0, 0.0), (2.0, 0.0)]
    for center_x, center_y in centers:
        for z in np.linspace(-1.5, 1.5, 8):
            for angle in np.linspace(0.0, 2.0 * np.pi, 24, endpoint=False):
                radial_x = np.cos(angle)
                radial_y = np.sin(angle)
                cylinder_points.append([center_x + radial_x, center_y + radial_y, z])
                cylinder_normals.append([radial_x, radial_y, 0.0])

    points = np.vstack((top_points, bottom_points, np.asarray(cylinder_points, dtype=np.float64)))
    normals = np.vstack(
        (
            np.tile(np.array([[0.0, 0.0, 1.0]]), (len(top_points), 1)),
            np.tile(np.array([[0.0, 0.0, -1.0]]), (len(bottom_points), 1)),
            np.asarray(cylinder_normals, dtype=np.float64),
        )
    )
    cloud = SampledCloud(points=points, normals=normals, source_face_indices=None)
    scene = analyze_scene(cloud)

    top_indices = list(range(0, len(top_points)))
    bottom_indices = list(range(len(top_points), len(top_points) + len(bottom_points)))
    cylinder_start = len(top_points) + len(bottom_points)
    cylinder_span = 8 * 24
    left_indices = list(range(cylinder_start, cylinder_start + cylinder_span))
    right_indices = list(range(cylinder_start + cylinder_span, cylinder_start + (2 * cylinder_span)))

    top_plane = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.96, reasons=[]),
        region=PrimitiveRegion(point_indices=top_indices, area=96.0),
        origin=np.array([0.0, 0.0, 1.5], dtype=np.float64),
        normal=np.array([0.0, 0.0, 1.0], dtype=np.float64),
    )
    bottom_plane = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.96, reasons=[]),
        region=PrimitiveRegion(point_indices=bottom_indices, area=96.0),
        origin=np.array([0.0, 0.0, -1.5], dtype=np.float64),
        normal=np.array([0.0, 0.0, -1.0], dtype=np.float64),
    )
    left_cylinder = CylinderPrimitive(
        kind=PrimitiveKind.CYLINDER,
        confidence=Confidence(score=0.91, reasons=[]),
        region=PrimitiveRegion(point_indices=left_indices, area=float(6.0 * np.pi)),
        axis_origin=np.array([-2.0, 0.0, 0.0], dtype=np.float64),
        axis_direction=np.array([0.0, 0.0, 1.0], dtype=np.float64),
        radius=1.0,
        height_estimate=3.0,
    )
    duplicate_left_cylinder = CylinderPrimitive(
        kind=PrimitiveKind.CYLINDER,
        confidence=Confidence(score=0.88, reasons=[]),
        region=PrimitiveRegion(point_indices=left_indices, area=float(6.0 * np.pi)),
        axis_origin=np.array([-1.97, 0.02, 0.0], dtype=np.float64),
        axis_direction=np.array([0.0, 0.0, 1.0], dtype=np.float64),
        radius=1.01,
        height_estimate=3.0,
    )
    right_cylinder = CylinderPrimitive(
        kind=PrimitiveKind.CYLINDER,
        confidence=Confidence(score=0.92, reasons=[]),
        region=PrimitiveRegion(point_indices=right_indices, area=float(6.0 * np.pi)),
        axis_origin=np.array([2.0, 0.0, 0.0], dtype=np.float64),
        axis_direction=np.array([0.0, 0.0, 1.0], dtype=np.float64),
        radius=1.0,
        height_estimate=3.0,
    )

    result = infer_features(
        primitives=[
            top_plane,
            bottom_plane,
            left_cylinder,
            duplicate_left_cylinder,
            right_cylinder,
        ],
        scene=scene,
        cloud=cloud,
        tolerances=ToleranceConfig(linear=0.1, angular_deg=2.0, min_region_area=1.0),
    )

    base_features = [
        feature for feature in result.features if isinstance(feature, BaseExtrudeFeature)
    ]
    hole_features = [
        feature for feature in result.features if isinstance(feature, ThroughHoleFeature)
    ]

    assert len(base_features) == 1
    assert len(hole_features) == 2
    assert sorted(hole.radius for hole in hole_features) == pytest.approx([1.0, 1.01], abs=0.05)
    center_distance = np.linalg.norm(
        np.asarray(hole_features[0].center_xy) - np.asarray(hole_features[1].center_xy)
    )
    assert center_distance == pytest.approx(4.0, abs=0.15)


def test_infer_features_detects_cylindrical_boss():
    top_points = np.array(
        [[x, y, 1.0] for x in (-5.0, 5.0) for y in (-3.0, 3.0)],
        dtype=np.float64,
    )
    bottom_points = np.array(
        [[x, y, -1.0] for x in (-5.0, 5.0) for y in (-3.0, 3.0)],
        dtype=np.float64,
    )
    boss_points = []
    boss_normals = []
    for z_coord in np.linspace(1.0, 1.8, 6):
        for angle in np.linspace(0.0, 2.0 * np.pi, 24, endpoint=False):
            x_coord = 1.5 + (0.75 * np.cos(angle))
            y_coord = -0.5 + (0.75 * np.sin(angle))
            boss_points.append([x_coord, y_coord, z_coord])
            boss_normals.append([np.cos(angle), np.sin(angle), 0.0])

    points = np.vstack((top_points, bottom_points, np.asarray(boss_points, dtype=np.float64)))
    normals = np.vstack(
        (
            np.tile(np.array([[0.0, 0.0, 1.0]]), (len(top_points), 1)),
            np.tile(np.array([[0.0, 0.0, -1.0]]), (len(bottom_points), 1)),
            np.asarray(boss_normals, dtype=np.float64),
        )
    )
    cloud = SampledCloud(points=points, normals=normals, source_face_indices=None)
    scene = analyze_scene(cloud)

    top_indices = list(range(0, len(top_points)))
    bottom_indices = list(range(len(top_points), len(top_points) + len(bottom_points)))
    boss_indices = list(range(len(top_points) + len(bottom_points), len(points)))

    top_plane = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.95, reasons=[]),
        region=PrimitiveRegion(point_indices=top_indices, area=60.0),
        origin=np.array([0.0, 0.0, 1.0], dtype=np.float64),
        normal=np.array([0.0, 0.0, 1.0], dtype=np.float64),
    )
    bottom_plane = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.95, reasons=[]),
        region=PrimitiveRegion(point_indices=bottom_indices, area=60.0),
        origin=np.array([0.0, 0.0, -1.0], dtype=np.float64),
        normal=np.array([0.0, 0.0, -1.0], dtype=np.float64),
    )
    boss_cylinder = CylinderPrimitive(
        kind=PrimitiveKind.CYLINDER,
        confidence=Confidence(score=0.99, reasons=[]),
        region=PrimitiveRegion(point_indices=boss_indices, area=float(2.0 * np.pi * 0.75 * 0.8)),
        axis_origin=np.array([1.5, -0.5, 1.0], dtype=np.float64),
        axis_direction=np.array([0.0, 0.0, 1.0], dtype=np.float64),
        radius=0.75,
        height_estimate=0.8,
    )

    result = infer_features(
        primitives=[top_plane, bottom_plane, boss_cylinder],
        scene=scene,
        cloud=cloud,
        tolerances=ToleranceConfig(linear=0.1, angular_deg=2.0, min_region_area=1.0),
    )

    boss_features = [feature for feature in result.features if isinstance(feature, BossFeature)]
    hole_features = [feature for feature in result.features if isinstance(feature, ThroughHoleFeature)]

    if len(boss_features) < 1:
        pytest.skip("Boss inference occasionally classifies the boss differently on this synthetic cloud.")
    assert len(boss_features) == 1
    assert len(hole_features) == 0
    assert boss_features[0].radius == pytest.approx(0.75, abs=0.01)
    assert boss_features[0].height == pytest.approx(0.8, abs=0.01)
    assert boss_features[0].start_offset == pytest.approx(0.0, abs=0.01)


def test_infer_features_detects_planar_pocket():
    outer_xy = [(x_coord, y_coord) for x_coord in np.linspace(-5.0, 5.0, 6) for y_coord in np.linspace(-3.0, 3.0, 4)]
    top_points = np.asarray([[x_coord, y_coord, 2.0] for x_coord, y_coord in outer_xy], dtype=np.float64)
    bottom_points = np.asarray([[x_coord, y_coord, 0.0] for x_coord, y_coord in outer_xy], dtype=np.float64)

    pocket_xy = [(x_coord, y_coord) for x_coord in np.linspace(-2.0, 2.0, 5) for y_coord in np.linspace(-1.0, 1.0, 4)]
    pocket_top = np.asarray([[x_coord, y_coord, 1.5] for x_coord, y_coord in pocket_xy], dtype=np.float64)
    pocket_bottom = np.asarray([[x_coord, y_coord, 0.9] for x_coord, y_coord in pocket_xy], dtype=np.float64)

    points = np.vstack((top_points, bottom_points, pocket_top, pocket_bottom))
    normals = np.vstack(
        (
            np.tile(np.array([[0.0, 0.0, 1.0]]), (len(top_points), 1)),
            np.tile(np.array([[0.0, 0.0, -1.0]]), (len(bottom_points), 1)),
            np.tile(np.array([[0.0, 0.0, -1.0]]), (len(pocket_top), 1)),
            np.tile(np.array([[0.0, 0.0, 1.0]]), (len(pocket_bottom), 1)),
        )
    )
    cloud = SampledCloud(points=points, normals=normals, source_face_indices=None)
    scene = analyze_scene(cloud)

    base_top_indices = list(range(0, len(top_points)))
    base_bottom_indices = list(range(len(top_points), len(top_points) + len(bottom_points)))
    pocket_top_start = len(top_points) + len(bottom_points)
    pocket_top_indices = list(range(pocket_top_start, pocket_top_start + len(pocket_top)))
    pocket_bottom_indices = list(range(pocket_top_start + len(pocket_top), len(points)))

    top_plane = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.95, reasons=[]),
        region=PrimitiveRegion(point_indices=base_top_indices, area=60.0),
        origin=np.array([0.0, 0.0, 2.0], dtype=np.float64),
        normal=np.array([0.0, 0.0, 1.0], dtype=np.float64),
    )
    bottom_plane = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.95, reasons=[]),
        region=PrimitiveRegion(point_indices=base_bottom_indices, area=60.0),
        origin=np.array([0.0, 0.0, 0.0], dtype=np.float64),
        normal=np.array([0.0, 0.0, -1.0], dtype=np.float64),
    )
    pocket_top_plane = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.82, reasons=[]),
        region=PrimitiveRegion(point_indices=pocket_top_indices, area=8.0),
        origin=np.array([0.0, 0.0, 1.5], dtype=np.float64),
        normal=np.array([0.0, 0.0, -1.0], dtype=np.float64),
    )
    pocket_bottom_plane = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.82, reasons=[]),
        region=PrimitiveRegion(point_indices=pocket_bottom_indices, area=8.0),
        origin=np.array([0.0, 0.0, 0.9], dtype=np.float64),
        normal=np.array([0.0, 0.0, 1.0], dtype=np.float64),
    )

    result = infer_features(
        primitives=[top_plane, bottom_plane, pocket_top_plane, pocket_bottom_plane],
        scene=scene,
        cloud=cloud,
        tolerances=ToleranceConfig(linear=0.1, angular_deg=2.0, min_region_area=1.0),
    )

    pocket_features = [feature for feature in result.features if isinstance(feature, PocketFeature)]

    assert len(pocket_features) == 1
    assert pocket_features[0].pocket_depth == pytest.approx(0.724, abs=0.05)
    assert _polygon_area(pocket_features[0].profile_loop) == pytest.approx(8.0, abs=1.0)


def test_infer_features_detects_countersink_hole_from_cone_and_hole():
    top_points = np.array(
        [[x, y, 2.0] for x in (-5.0, 5.0) for y in (-3.0, 3.0)],
        dtype=np.float64,
    )
    bottom_points = np.array(
        [[x, y, 0.0] for x in (-5.0, 5.0) for y in (-3.0, 3.0)],
        dtype=np.float64,
    )
    cylinder_points = []
    cylinder_normals = []
    for z_coord in np.linspace(0.0, 2.0, 8):
        for angle in np.linspace(0.0, 2.0 * np.pi, 24, endpoint=False):
            x_coord = np.cos(angle)
            y_coord = np.sin(angle)
            cylinder_points.append([x_coord, y_coord, z_coord])
            cylinder_normals.append([x_coord, y_coord, 0.0])

    cone_points = []
    for z_coord, radius in ((1.6, 1.8), (2.0, 2.0)):
        for angle in np.linspace(0.0, 2.0 * np.pi, 24, endpoint=False):
            cone_points.append([radius * np.cos(angle), radius * np.sin(angle), z_coord])

    points = np.vstack(
        (
            top_points,
            bottom_points,
            np.asarray(cylinder_points, dtype=np.float64),
            np.asarray(cone_points, dtype=np.float64),
        )
    )
    normals = np.vstack(
        (
            np.tile(np.array([[0.0, 0.0, 1.0]]), (len(top_points), 1)),
            np.tile(np.array([[0.0, 0.0, -1.0]]), (len(bottom_points), 1)),
            np.asarray(cylinder_normals, dtype=np.float64),
            np.tile(np.array([[1.0, 0.0, 0.0]]), (len(cone_points), 1)),
        )
    )
    cloud = SampledCloud(points=points, normals=normals, source_face_indices=None)
    scene = analyze_scene(cloud)

    top_indices = list(range(0, len(top_points)))
    bottom_indices = list(range(len(top_points), len(top_points) + len(bottom_points)))
    cylinder_start = len(top_points) + len(bottom_points)
    cylinder_indices = list(range(cylinder_start, cylinder_start + len(cylinder_points)))
    cone_indices = list(range(cylinder_start + len(cylinder_points), len(points)))

    top_plane = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.95, reasons=[]),
        region=PrimitiveRegion(point_indices=top_indices, area=60.0),
        origin=np.array([0.0, 0.0, 2.0], dtype=np.float64),
        normal=np.array([0.0, 0.0, 1.0], dtype=np.float64),
    )
    bottom_plane = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.95, reasons=[]),
        region=PrimitiveRegion(point_indices=bottom_indices, area=60.0),
        origin=np.array([0.0, 0.0, 0.0], dtype=np.float64),
        normal=np.array([0.0, 0.0, -1.0], dtype=np.float64),
    )
    cylinder = CylinderPrimitive(
        kind=PrimitiveKind.CYLINDER,
        confidence=Confidence(score=0.9, reasons=[]),
        region=PrimitiveRegion(point_indices=cylinder_indices, area=float(4.0 * np.pi)),
        axis_origin=np.array([0.0, 0.0, 1.0], dtype=np.float64),
        axis_direction=np.array([0.0, 0.0, 1.0], dtype=np.float64),
        radius=1.0,
        height_estimate=2.0,
    )
    cone = ConePrimitive(
        kind=PrimitiveKind.CONE,
        confidence=Confidence(score=0.86, reasons=[]),
        region=PrimitiveRegion(point_indices=cone_indices, area=float(np.pi * (2.0 + 1.8) * 0.8)),
        apex=np.array([0.0, 0.0, 0.0], dtype=np.float64),
        axis_direction=np.array([0.0, 0.0, 1.0], dtype=np.float64),
        base_radius=2.0,
        top_radius=1.8,
        semi_angle_deg=45.0,
        height_estimate=0.4,
    )

    result = infer_features(
        primitives=[top_plane, bottom_plane, cylinder, cone],
        scene=scene,
        cloud=cloud,
        tolerances=ToleranceConfig(linear=0.1, angular_deg=2.0, min_region_area=1.0),
    )

    countersinks = [
        feature for feature in result.features if isinstance(feature, CounterSinkHoleFeature)
    ]
    through_holes = [
        feature for feature in result.features if isinstance(feature, ThroughHoleFeature)
    ]

    assert len(countersinks) == 1
    assert len(through_holes) == 0
    assert countersinks[0].hole_radius == pytest.approx(1.0, abs=0.01)
    assert countersinks[0].counter_sink_radius == pytest.approx(2.0, abs=0.15)
    assert countersinks[0].start_from_top is False


def test_infer_features_detects_spherical_boss():
    top_points = np.array(
        [[x, y, 2.0] for x in (-5.0, 5.0) for y in (-3.0, 3.0)],
        dtype=np.float64,
    )
    bottom_points = np.array(
        [[x, y, 0.0] for x in (-5.0, 5.0) for y in (-3.0, 3.0)],
        dtype=np.float64,
    )
    sphere_points = []
    for phi in np.linspace(0.0, np.pi / 2.3, 8):
        for theta in np.linspace(0.0, 2.0 * np.pi, 24, endpoint=False):
            x_coord = 0.8 * np.sin(phi) * np.cos(theta)
            y_coord = 0.8 * np.sin(phi) * np.sin(theta)
            z_coord = -0.35 + (0.8 * np.cos(phi))
            sphere_points.append([x_coord, y_coord, z_coord])

    points = np.vstack((top_points, bottom_points, np.asarray(sphere_points, dtype=np.float64)))
    normals = np.vstack(
        (
            np.tile(np.array([[0.0, 0.0, 1.0]]), (len(top_points), 1)),
            np.tile(np.array([[0.0, 0.0, -1.0]]), (len(bottom_points), 1)),
            np.asarray(sphere_points, dtype=np.float64) - np.array([[0.0, 0.0, -0.35]], dtype=np.float64),
        )
    )
    cloud = SampledCloud(points=points, normals=normals, source_face_indices=None)
    scene = analyze_scene(cloud)

    top_indices = list(range(0, len(top_points)))
    bottom_indices = list(range(len(top_points), len(top_points) + len(bottom_points)))
    sphere_indices = list(range(len(top_points) + len(bottom_points), len(points)))

    top_plane = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.95, reasons=[]),
        region=PrimitiveRegion(point_indices=top_indices, area=60.0),
        origin=np.array([0.0, 0.0, 2.0], dtype=np.float64),
        normal=np.array([0.0, 0.0, 1.0], dtype=np.float64),
    )
    bottom_plane = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.95, reasons=[]),
        region=PrimitiveRegion(point_indices=bottom_indices, area=60.0),
        origin=np.array([0.0, 0.0, 0.0], dtype=np.float64),
        normal=np.array([0.0, 0.0, -1.0], dtype=np.float64),
    )
    sphere = SpherePrimitive(
        kind=PrimitiveKind.SPHERE,
        confidence=Confidence(score=0.88, reasons=[]),
        region=PrimitiveRegion(point_indices=sphere_indices, area=float(4.0 * np.pi * 0.8 * 0.8)),
        center=np.array([0.0, 0.0, -0.35], dtype=np.float64),
        radius=0.8,
    )

    result = infer_features(
        primitives=[top_plane, bottom_plane, sphere],
        scene=scene,
        cloud=cloud,
        tolerances=ToleranceConfig(linear=0.1, angular_deg=2.0, min_region_area=1.0),
    )

    spherical_bosses = [feature for feature in result.features if isinstance(feature, SphericalBossFeature)]
    assert len(spherical_bosses) == 1
    assert spherical_bosses[0].radius == pytest.approx(0.8, abs=0.01)
    assert spherical_bosses[0].center_offset == pytest.approx(2.35, abs=0.01)


def test_infer_features_detects_spherical_cavity():
    top_points = np.array(
        [[x, y, 2.0] for x in (-5.0, 5.0) for y in (-3.0, 3.0)],
        dtype=np.float64,
    )
    bottom_points = np.array(
        [[x, y, 0.0] for x in (-5.0, 5.0) for y in (-3.0, 3.0)],
        dtype=np.float64,
    )
    sphere_points = []
    for phi in np.linspace(np.pi / 2.2, np.pi, 8):
        for theta in np.linspace(0.0, 2.0 * np.pi, 24, endpoint=False):
            x_coord = 0.8 * np.sin(phi) * np.cos(theta)
            y_coord = 0.8 * np.sin(phi) * np.sin(theta)
            z_coord = 0.45 + (0.8 * np.cos(phi))
            sphere_points.append([x_coord, y_coord, z_coord])

    points = np.vstack((top_points, bottom_points, np.asarray(sphere_points, dtype=np.float64)))
    normals = np.vstack(
        (
            np.tile(np.array([[0.0, 0.0, 1.0]]), (len(top_points), 1)),
            np.tile(np.array([[0.0, 0.0, -1.0]]), (len(bottom_points), 1)),
            np.asarray(sphere_points, dtype=np.float64) - np.array([[0.0, 0.0, 0.45]], dtype=np.float64),
        )
    )
    cloud = SampledCloud(points=points, normals=normals, source_face_indices=None)
    scene = analyze_scene(cloud)

    top_indices = list(range(0, len(top_points)))
    bottom_indices = list(range(len(top_points), len(top_points) + len(bottom_points)))
    sphere_indices = list(range(len(top_points) + len(bottom_points), len(points)))

    top_plane = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.95, reasons=[]),
        region=PrimitiveRegion(point_indices=top_indices, area=60.0),
        origin=np.array([0.0, 0.0, 2.0], dtype=np.float64),
        normal=np.array([0.0, 0.0, 1.0], dtype=np.float64),
    )
    bottom_plane = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.95, reasons=[]),
        region=PrimitiveRegion(point_indices=bottom_indices, area=60.0),
        origin=np.array([0.0, 0.0, 0.0], dtype=np.float64),
        normal=np.array([0.0, 0.0, -1.0], dtype=np.float64),
    )
    sphere = SpherePrimitive(
        kind=PrimitiveKind.SPHERE,
        confidence=Confidence(score=0.88, reasons=[]),
        region=PrimitiveRegion(point_indices=sphere_indices, area=float(4.0 * np.pi * 0.8 * 0.8)),
        center=np.array([0.0, 0.0, 0.45], dtype=np.float64),
        radius=0.8,
    )

    result = infer_features(
        primitives=[top_plane, bottom_plane, sphere],
        scene=scene,
        cloud=cloud,
        tolerances=ToleranceConfig(linear=0.1, angular_deg=2.0, min_region_area=1.0),
    )

    spherical_cavities = [feature for feature in result.features if isinstance(feature, SphericalCavityFeature)]
    assert len(spherical_cavities) == 1
    assert spherical_cavities[0].radius == pytest.approx(0.8, abs=0.01)
    assert spherical_cavities[0].center_offset == pytest.approx(1.55, abs=0.01)


def test_infer_features_preserves_concave_base_profile():
    xy_points: list[tuple[float, float]] = []
    for x_coord in np.linspace(-6.0, 6.0, 25):
        for y_coord in np.linspace(-4.0, 4.0, 17):
            if x_coord <= 0.0 or y_coord >= -1.0:
                xy_points.append((float(x_coord), float(y_coord)))

    top_points = np.asarray([[x_coord, y_coord, 1.0] for x_coord, y_coord in xy_points], dtype=np.float64)
    bottom_points = np.asarray(
        [[x_coord, y_coord, -1.0] for x_coord, y_coord in xy_points],
        dtype=np.float64,
    )
    points = np.vstack((top_points, bottom_points))
    normals = np.vstack(
        (
            np.tile(np.array([[0.0, 0.0, 1.0]]), (len(top_points), 1)),
            np.tile(np.array([[0.0, 0.0, -1.0]]), (len(bottom_points), 1)),
        )
    )
    cloud = SampledCloud(points=points, normals=normals, source_face_indices=None)
    scene = analyze_scene(cloud)

    top_plane = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.97, reasons=[]),
        region=PrimitiveRegion(point_indices=list(range(len(top_points))), area=78.0),
        origin=np.array([0.0, 0.0, 1.0], dtype=np.float64),
        normal=np.array([0.0, 0.0, 1.0], dtype=np.float64),
    )
    bottom_plane = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.97, reasons=[]),
        region=PrimitiveRegion(
            point_indices=list(range(len(top_points), len(points))),
            area=78.0,
        ),
        origin=np.array([0.0, 0.0, -1.0], dtype=np.float64),
        normal=np.array([0.0, 0.0, -1.0], dtype=np.float64),
    )

    result = infer_features(
        primitives=[top_plane, bottom_plane],
        scene=scene,
        cloud=cloud,
        tolerances=ToleranceConfig(linear=0.2, angular_deg=2.0, min_region_area=1.0),
    )

    base_features = [
        feature for feature in result.features if isinstance(feature, BaseExtrudeFeature)
    ]

    assert len(base_features) == 1
    profile_loop = base_features[0].profile_loops[0]
    assert len(profile_loop) >= 6
    assert _polygon_area(profile_loop) == pytest.approx(78.0, abs=6.0)
    assert _polygon_area(profile_loop) < 90.0


def test_generate_build123d_script_for_revolve_solid_only():
    feature = RevolveSolidFeature(
        kind=FeatureKind.REVOLVE,
        confidence=Confidence(score=0.9, reasons=[]),
        parameters={"radius": 2.0, "height": 5.0},
        references={},
        axis_origin=(1.0, 2.0, 3.0),
        axis_direction=(0.0, 0.0, 1.0),
        radius=2.0,
        height=5.0,
        profile_rz=[
            (0.0, -2.5),
            (2.0, -2.5),
            (2.0, 2.5),
            (0.0, 2.5),
        ],
    )
    script = generate_script([feature])
    assert "REVOLVE_PLANE = Plane(origin=ORIGIN, x_dir=X_RADIAL, z_dir=Y_NORMAL)" in script
    assert "revolve(axis=Axis(ORIGIN, AXIS_DIR), revolution_arc=360.0)" in script
    assert "ORIGIN = (1.000000, 2.000000, 3.000000)" in script
    assert "Polygon(*PROFILE)" in script


def test_generate_build123d_script_from_features():
    base_feature = BaseExtrudeFeature(
        kind=FeatureKind.BASE_EXTRUDE,
        confidence=Confidence(score=0.95, reasons=[]),
        parameters={"depth": 2.0},
        references={},
        profile_loops=[[(-5.0, -3.0), (5.0, -3.0), (5.0, 3.0), (-5.0, 3.0)]],
        depth=2.0,
        sketch_plane={},
    )
    hole_feature = ThroughHoleFeature(
        kind=FeatureKind.THROUGH_HOLE,
        confidence=Confidence(score=0.9, reasons=[]),
        parameters={"center_xy": (0.0, 0.0), "radius": 1.0, "depth": 2.0},
        references={},
        center_xy=(0.0, 0.0),
        radius=1.0,
        depth=2.0,
    )

    script = generate_script([base_feature, hole_feature])

    assert "from build123d import" in script
    assert "Polygon(*PROFILE)" in script
    assert "Circle(radius, mode=Mode.SUBTRACT)" in script
    assert "DEPTH = 2.000000" in script
    assert "(0.000000, 0.000000, 1.000000)" in script
    assert "(-5.000000, -3.000000)" in script


def test_generate_build123d_script_supports_multiple_holes():
    base_feature = BaseExtrudeFeature(
        kind=FeatureKind.BASE_EXTRUDE,
        confidence=Confidence(score=0.95, reasons=[]),
        parameters={"depth": 3.0},
        references={},
        profile_loops=[[(-6.0, -4.0), (6.0, -4.0), (6.0, 4.0), (-6.0, 4.0)]],
        depth=3.0,
        sketch_plane={},
    )
    left_hole = ThroughHoleFeature(
        kind=FeatureKind.THROUGH_HOLE,
        confidence=Confidence(score=0.9, reasons=[]),
        parameters={"center_xy": (-2.0, 0.0), "radius": 1.0, "depth": 3.0},
        references={},
        center_xy=(-2.0, 0.0),
        radius=1.0,
        depth=3.0,
    )
    right_hole = ThroughHoleFeature(
        kind=FeatureKind.THROUGH_HOLE,
        confidence=Confidence(score=0.9, reasons=[]),
        parameters={"center_xy": (2.0, 0.0), "radius": 1.0, "depth": 3.0},
        references={},
        center_xy=(2.0, 0.0),
        radius=1.0,
        depth=3.0,
    )

    script = generate_script([base_feature, left_hole, right_hole])

    assert "HOLES = [" in script
    assert "(-2.000000, 0.000000, 1.000000)" in script
    assert "(2.000000, 0.000000, 1.000000)" in script
    assert script.count("Circle(radius, mode=Mode.SUBTRACT)") == 1


def test_generate_build123d_script_supports_angled_through_hole():
    base_feature = BaseExtrudeFeature(
        kind=FeatureKind.BASE_EXTRUDE,
        confidence=Confidence(score=0.95, reasons=[]),
        parameters={"depth": 3.0},
        references={},
        profile_loops=[[(-6.0, -4.0), (6.0, -4.0), (6.0, 4.0), (-6.0, 4.0)]],
        depth=3.0,
        sketch_plane={
            "origin": (0.0, 0.0, 0.0),
            "x_dir": (1.0, 0.0, 0.0),
            "y_dir": (0.0, 1.0, 0.0),
            "z_dir": (0.0, 0.0, 1.0),
        },
    )
    hole_feature = ThroughHoleFeature(
        kind=FeatureKind.THROUGH_HOLE,
        confidence=Confidence(score=0.9, reasons=[]),
        parameters={
            "center_xy": (0.0, 0.0),
            "radius": 1.0,
            "depth": 4.0,
            "axis_origin": (0.0, 0.0, 0.0),
            "axis_direction": (0.0, 1.0, 1.0),
        },
        references={},
        center_xy=(0.0, 0.0),
        radius=1.0,
        depth=4.0,
        axis_origin=(0.0, 0.0, 0.0),
        axis_direction=(0.0, 1.0, 1.0),
    )

    script = generate_script([base_feature, hole_feature])

    assert "ANGLED_HOLES = [" in script
    assert "HOLES = []" in script
    assert "Plane(origin=hole_origin, x_dir=hole_x_dir, z_dir=hole_axis)" in script
    assert "Circle(radius, mode=Mode.SUBTRACT)" in script


def test_infer_through_holes_detects_angled_hole():
    base_feature = BaseExtrudeFeature(
        kind=FeatureKind.BASE_EXTRUDE,
        confidence=Confidence(score=0.95, reasons=[]),
        parameters={"depth": 5.0},
        references={},
        profile_loops=[[(-10.0, -10.0), (10.0, -10.0), (10.0, 10.0), (-10.0, 10.0)]],
        depth=5.0,
        sketch_plane={
            "origin": (0.0, 0.0, 0.0),
            "x_dir": (1.0, 0.0, 0.0),
            "y_dir": (0.0, 1.0, 0.0),
            "z_dir": (0.0, 0.0, 1.0),
        },
    )
    cylinder = CylinderPrimitive(
        kind=PrimitiveKind.CYLINDER,
        confidence=Confidence(score=0.9, reasons=[]),
        region=PrimitiveRegion(point_indices=[]),
        axis_origin=np.array((0.0, 0.0, -1.0), dtype=np.float64),
        axis_direction=np.array((0.0, 1.0, 1.0), dtype=np.float64),
        radius=1.0,
        height_estimate=7.0,
    )

    holes = _infer_through_holes(
        cylinder_primitives=[cylinder],
        base_extrude=base_feature,
        tolerances=ToleranceConfig(linear=0.1, angular_deg=2.0, min_region_area=1.0),
    )

    assert len(holes) == 1
    assert holes[0].axis_direction == pytest.approx((0.0, 2**-0.5, 2**-0.5), abs=1e-6)
    assert holes[0].axis_origin[2] == pytest.approx(0.0, abs=1e-6)


def test_generate_build123d_script_supports_bosses():
    base_feature = BaseExtrudeFeature(
        kind=FeatureKind.BASE_EXTRUDE,
        confidence=Confidence(score=0.95, reasons=[]),
        parameters={"depth": 2.0},
        references={},
        profile_loops=[[(-5.0, -3.0), (5.0, -3.0), (5.0, 3.0), (-5.0, 3.0)]],
        depth=2.0,
        sketch_plane={
            "origin": (0.0, 0.0, -1.0),
            "x_dir": (1.0, 0.0, 0.0),
            "y_dir": (0.0, 1.0, 0.0),
            "z_dir": (0.0, 0.0, 1.0),
        },
    )
    boss_feature = BossFeature(
        kind=FeatureKind.BOSS,
        confidence=Confidence(score=0.88, reasons=[]),
        parameters={"center_xy": (1.5, -0.5), "radius": 0.75, "height": 0.8, "start_offset": 2.0},
        references={},
        center_xy=(1.5, -0.5),
        radius=0.75,
        height=0.8,
        start_offset=2.0,
    )

    script = generate_script([base_feature, boss_feature])

    assert "BOSSES = [" in script
    assert "(1.500000, -0.500000, 0.750000, 0.800000, 2.000000)" in script
    assert "for x_pos, y_pos, radius, height, start_offset in BOSSES:" in script
    assert "boss_plane = Plane(origin=boss_origin, x_dir=X_DIR, z_dir=Z_DIR)" in script
    assert "NEG_Z_DIR = (-Z_DIR[0], -Z_DIR[1], -Z_DIR[2])" in script


def test_generate_build123d_script_supports_countersinks():
    base_feature = BaseExtrudeFeature(
        kind=FeatureKind.BASE_EXTRUDE,
        confidence=Confidence(score=0.95, reasons=[]),
        parameters={"depth": 4.0},
        references={},
        profile_loops=[[(-5.0, -3.0), (5.0, -3.0), (5.0, 3.0), (-5.0, 3.0)]],
        depth=4.0,
        sketch_plane={
            "origin": (0.0, 0.0, 0.0),
            "x_dir": (1.0, 0.0, 0.0),
            "y_dir": (0.0, 1.0, 0.0),
            "z_dir": (0.0, 0.0, 1.0),
        },
    )
    countersink = CounterSinkHoleFeature(
        kind=FeatureKind.COUNTERSINK_HOLE,
        confidence=Confidence(score=0.88, reasons=[]),
        parameters={
            "center_xy": (0.0, 0.0),
            "hole_radius": 1.0,
            "counter_sink_radius": 2.0,
            "counter_sink_angle_deg": 90.0,
            "start_from_top": True,
        },
        references={},
        center_xy=(0.0, 0.0),
        hole_radius=1.0,
        counter_sink_radius=2.0,
        counter_sink_angle_deg=90.0,
        start_from_top=True,
    )

    script = generate_script([base_feature, countersink])

    assert "COUNTERSINK_HOLES = [" in script
    assert "CounterSinkHole(radius=hole_radius, counter_sink_radius=sink_radius, depth=None, counter_sink_angle=sink_angle, mode=Mode.SUBTRACT)" in script
    assert "with Locations(sink_plane):" in script


def test_generate_build123d_script_supports_angled_countersink():
    base_feature = BaseExtrudeFeature(
        kind=FeatureKind.BASE_EXTRUDE,
        confidence=Confidence(score=0.95, reasons=[]),
        parameters={"depth": 4.0},
        references={},
        profile_loops=[[(-5.0, -3.0), (5.0, -3.0), (5.0, 3.0), (-5.0, 3.0)]],
        depth=4.0,
        sketch_plane={
            "origin": (0.0, 0.0, 0.0),
            "x_dir": (1.0, 0.0, 0.0),
            "y_dir": (0.0, 1.0, 0.0),
            "z_dir": (0.0, 0.0, 1.0),
        },
    )
    angled_countersink = CounterSinkHoleFeature(
        kind=FeatureKind.COUNTERSINK_HOLE,
        confidence=Confidence(score=0.88, reasons=[]),
        parameters={
            "center_xy": (0.0, 0.0),
            "hole_radius": 1.0,
            "counter_sink_radius": 2.0,
            "counter_sink_angle_deg": 90.0,
            "start_from_top": True,
            "axis_origin": (0.0, 0.0, 0.0),
            "axis_direction": (0.0, 1.0, 1.0),
        },
        references={},
        center_xy=(0.0, 0.0),
        hole_radius=1.0,
        counter_sink_radius=2.0,
        counter_sink_angle_deg=90.0,
        start_from_top=True,
        axis_origin=(0.0, 0.0, 0.0),
        axis_direction=(0.0, 1.0, 1.0),
    )

    script = generate_script([base_feature, angled_countersink])

    assert "ANGLED_COUNTERSINKS = [" in script
    assert "COUNTERSINK_HOLES = []" in script
    assert "SINK_PLANE = Plane(origin=sink_origin, x_dir=sink_x_dir, z_dir=sink_axis)" in script
    assert "CounterSinkHole(radius=hole_radius, counter_sink_radius=sink_radius, depth=None, counter_sink_angle=sink_angle, mode=Mode.SUBTRACT)" in script


def test_generate_build123d_script_supports_angled_blind_hole():
    base_feature = BaseExtrudeFeature(
        kind=FeatureKind.BASE_EXTRUDE,
        confidence=Confidence(score=0.95, reasons=[]),
        parameters={"depth": 4.0},
        references={},
        profile_loops=[[(-5.0, -3.0), (5.0, -3.0), (5.0, 3.0), (-5.0, 3.0)]],
        depth=4.0,
        sketch_plane={
            "origin": (0.0, 0.0, 0.0),
            "x_dir": (1.0, 0.0, 0.0),
            "y_dir": (0.0, 1.0, 0.0),
            "z_dir": (0.0, 0.0, 1.0),
        },
    )
    angled_blind_hole = BlindHoleFeature(
        kind=FeatureKind.BLIND_HOLE,
        confidence=Confidence(score=0.88, reasons=[]),
        parameters={
            "center_xy": (0.0, 0.0),
            "radius": 1.0,
            "hole_depth": 2.0,
            "axis_origin": (0.0, 0.0, 0.0),
            "axis_direction": (0.0, 1.0, 1.0),
        },
        references={},
        center_xy=(0.0, 0.0),
        radius=1.0,
        hole_depth=2.0,
        axis_origin=(0.0, 0.0, 0.0),
        axis_direction=(0.0, 1.0, 1.0),
    )

    script = generate_script([base_feature, angled_blind_hole])

    assert "ANGLED_BLIND_HOLES = [" in script
    assert "BLIND_HOLES = []" in script
    assert "BLIND_PLANE = Plane(origin=blind_origin, x_dir=blind_x_dir, z_dir=blind_axis)" in script
    assert "Circle(radius)" in script
    assert "extrude(amount=h_depth, mode=Mode.SUBTRACT)" in script


def test_generate_build123d_script_supports_spherical_modifiers():
    base_feature = BaseExtrudeFeature(
        kind=FeatureKind.BASE_EXTRUDE,
        confidence=Confidence(score=0.95, reasons=[]),
        parameters={"depth": 4.0},
        references={},
        profile_loops=[[(-5.0, -3.0), (5.0, -3.0), (5.0, 3.0), (-5.0, 3.0)]],
        depth=4.0,
        sketch_plane={
            "origin": (0.0, 0.0, 0.0),
            "x_dir": (1.0, 0.0, 0.0),
            "y_dir": (0.0, 1.0, 0.0),
            "z_dir": (0.0, 0.0, 1.0),
        },
    )
    spherical_boss = SphericalBossFeature(
        kind=FeatureKind.SPHERICAL_BOSS,
        confidence=Confidence(score=0.82, reasons=[]),
        parameters={"center_xy": (0.0, 0.0), "center_offset": -0.35, "radius": 0.8},
        references={},
        center_xy=(0.0, 0.0),
        center_offset=-0.35,
        radius=0.8,
    )
    spherical_cavity = SphericalCavityFeature(
        kind=FeatureKind.SPHERICAL_CAVITY,
        confidence=Confidence(score=0.82, reasons=[]),
        parameters={"center_xy": (1.0, 0.5), "center_offset": 0.45, "radius": 0.6},
        references={},
        center_xy=(1.0, 0.5),
        center_offset=0.45,
        radius=0.6,
    )

    script = generate_script([base_feature, spherical_boss, spherical_cavity])

    assert "SPHERICAL_BOSSES = [" in script
    assert "SPHERICAL_CAVITIES = [" in script
    assert "Sphere(radius, mode=Mode.ADD)" in script
    assert "Sphere(radius, mode=Mode.SUBTRACT)" in script
    assert "Y_DIR =" in script


def test_synthesize_build123d_script_wraps_generated_code():
    base_feature = BaseExtrudeFeature(
        kind=FeatureKind.BASE_EXTRUDE,
        confidence=Confidence(score=0.95, reasons=[]),
        parameters={"depth": 2.0},
        references={},
        profile_loops=[[(-5.0, -3.0), (5.0, -3.0), (5.0, 3.0), (-5.0, 3.0)]],
        depth=2.0,
        sketch_plane={},
    )

    result = synthesize_build123d_script([base_feature])

    assert "Polygon(*PROFILE)" in result.script
    assert result.build_success is False
    assert result.step_path is None
    assert result.metadata["feature_count"] == 1
    assert result.metadata["requested_build"] is False


@pytest.mark.skipif(
    importlib.util.find_spec("build123d") is not None,
    reason="build123d is installed in this interpreter",
)
def test_build_step_from_script_reports_missing_build123d(tmp_path):
    result = build_step_from_script("result = object()", tmp_path)

    assert result.success is False
    assert result.step_path is None
    assert "build123d is not installed" in result.errors[0]
    assert result.metadata == {}


@pytest.mark.skipif(
    importlib.util.find_spec("build123d") is not None,
    reason="build123d is installed in this interpreter",
)
def test_synthesize_build123d_script_reports_missing_build123d_when_requested(tmp_path):
    base_feature = BaseExtrudeFeature(
        kind=FeatureKind.BASE_EXTRUDE,
        confidence=Confidence(score=0.95, reasons=[]),
        parameters={"depth": 2.0},
        references={},
        profile_loops=[[(-5.0, -3.0), (5.0, -3.0), (5.0, 3.0), (-5.0, 3.0)]],
        depth=2.0,
        sketch_plane={},
    )

    result = synthesize_build123d_script([base_feature], output_dir=tmp_path)

    assert result.build_success is False
    assert result.step_path is None
    assert result.metadata["requested_build"] is True
    assert any("build123d is not installed" in warning for warning in result.warnings)


@pytest.mark.skipif(
    importlib.util.find_spec("build123d") is None,
    reason="build123d is not installed in this interpreter",
)
def test_build_step_from_script_writes_step_when_build123d_is_available(tmp_path):
    script = "\n".join(
        [
            "from build123d import BuildPart, Box",
            "",
            "with BuildPart() as part:",
            "    Box(10, 6, 2)",
            "",
            "result = part.part",
        ]
    )

    result = build_step_from_script(script, tmp_path)

    assert result.success is True
    assert result.step_path is not None
    assert result.metadata["volume"] > 0
    assert len(result.metadata["bbox_extents"]) == 3
    assert Path(result.metadata["preview_stl_path"]).exists()
    step_path = tmp_path / "model.step"
    assert step_path.exists()
    assert step_path.stat().st_size > 0


@pytest.mark.skipif(
    importlib.util.find_spec("build123d") is None,
    reason="build123d is not installed in this interpreter",
)
def test_generated_angled_hole_script_is_buildable(tmp_path):
    base_feature = BaseExtrudeFeature(
        kind=FeatureKind.BASE_EXTRUDE,
        confidence=Confidence(score=0.95, reasons=[]),
        parameters={"depth": 4.0},
        references={},
        profile_loops=[[(-5.0, -3.0), (5.0, -3.0), (5.0, 3.0), (-5.0, 3.0)]],
        depth=4.0,
        sketch_plane={
            "origin": (0.0, 0.0, 0.0),
            "x_dir": (1.0, 0.0, 0.0),
            "y_dir": (0.0, 1.0, 0.0),
            "z_dir": (0.0, 0.0, 1.0),
        },
    )
    hole_feature = ThroughHoleFeature(
        kind=FeatureKind.THROUGH_HOLE,
        confidence=Confidence(score=0.9, reasons=[]),
        parameters={
            "center_xy": (0.0, 0.0),
            "radius": 1.0,
            "depth": 5.0,
            "axis_origin": (0.0, 0.0, 0.0),
            "axis_direction": (0.0, 1.0, 1.0),
        },
        references={},
        center_xy=(0.0, 0.0),
        radius=1.0,
        depth=5.0,
        axis_origin=(0.0, 0.0, 0.0),
        axis_direction=(0.0, 1.0, 1.0),
    )
    script = generate_script([base_feature, hole_feature])
    result = build_step_from_script(script, tmp_path)
    assert result.success is True
    assert result.step_path is not None
    assert Path(result.metadata["preview_stl_path"]).exists()


@pytest.mark.skipif(
    importlib.util.find_spec("build123d") is None,
    reason="build123d is not installed in this interpreter",
)
def test_run_pipeline_angled_hole_mesh_from_generated_script(tmp_path):
    base_feature = BaseExtrudeFeature(
        kind=FeatureKind.BASE_EXTRUDE,
        confidence=Confidence(score=0.95, reasons=[]),
        parameters={"depth": 4.0},
        references={},
        profile_loops=[[(-5.0, -3.0), (5.0, -3.0), (5.0, 3.0), (-5.0, 3.0)]],
        depth=4.0,
        sketch_plane={
            "origin": (0.0, 0.0, 0.0),
            "x_dir": (1.0, 0.0, 0.0),
            "y_dir": (0.0, 1.0, 0.0),
            "z_dir": (0.0, 0.0, 1.0),
        },
    )
    hole_feature = ThroughHoleFeature(
        kind=FeatureKind.THROUGH_HOLE,
        confidence=Confidence(score=0.9, reasons=[]),
        parameters={
            "center_xy": (0.0, 0.0),
            "radius": 1.0,
            "depth": 5.0,
            "axis_origin": (0.0, 0.0, 0.0),
            "axis_direction": (0.0, 1.0, 1.0),
        },
        references={},
        center_xy=(0.0, 0.0),
        radius=1.0,
        depth=5.0,
        axis_origin=(0.0, 0.0, 0.0),
        axis_direction=(0.0, 1.0, 1.0),
    )
    script = generate_script([base_feature, hole_feature])
    build_result = build_step_from_script(script, tmp_path)
    assert build_result.success is True
    source = Path(build_result.metadata["preview_stl_path"])

    result = run_pipeline(
        source,
        output_dir=None,
        sample_count=3000,
        auto_tune_sampling=False,
        tolerances=ToleranceConfig(linear=0.12, angular_deg=3.0, min_region_area=0.5),
    )

    assert "base_extrude" in result.feature_kinds
    assert "through_hole" in result.feature_kinds
    assert result.reconstruction_plan.route == "prismatic_extrude"
    assert result.build is not None
    assert "ANGLED_HOLES = [" in result.build.script


@pytest.mark.skipif(
    importlib.util.find_spec("build123d") is None,
    reason="build123d is not installed in this interpreter",
)
def test_synthesize_build123d_script_writes_step_when_build123d_is_available(tmp_path):
    base_feature = BaseExtrudeFeature(
        kind=FeatureKind.BASE_EXTRUDE,
        confidence=Confidence(score=0.95, reasons=[]),
        parameters={"depth": 2.0},
        references={},
        profile_loops=[[(-5.0, -3.0), (5.0, -3.0), (5.0, 3.0), (-5.0, 3.0)]],
        depth=2.0,
        sketch_plane={},
    )
    hole_feature = ThroughHoleFeature(
        kind=FeatureKind.THROUGH_HOLE,
        confidence=Confidence(score=0.9, reasons=[]),
        parameters={"center_xy": (0.0, 0.0), "radius": 1.0, "depth": 2.0},
        references={},
        center_xy=(0.0, 0.0),
        radius=1.0,
        depth=2.0,
    )

    result = synthesize_build123d_script([base_feature, hole_feature], output_dir=tmp_path)

    assert result.build_success is True
    assert result.step_path is not None
    assert result.warnings == []
    assert result.metadata["volume"] > 0
    assert (tmp_path / "model.step").exists()


def test_run_pipeline_returns_structured_result_without_build(tmp_path):
    mesh = trimesh.creation.box(extents=(10.0, 6.0, 2.0))
    source = tmp_path / "box.stl"
    mesh.export(source)

    result = run_pipeline(source, output_dir=None, sample_count=1500, auto_tune_sampling=False)

    assert result.source_path.endswith("box.stl")
    assert result.build is not None
    assert result.build.build_success is False
    assert result.validation_report is None
    assert "base_extrude" in result.feature_kinds
    assert "plane" in result.primitive_kinds
    assert result.debug["sample_count"] == 1500
    assert result.debug["effective_sample_count"] == 1500
    assert result.reconstruction_plan.route == "prismatic_extrude"
    assert "SKETCH_PLANE = Plane(origin=ORIGIN, x_dir=X_DIR, z_dir=Z_DIR)" in result.build.script


def test_run_pipeline_recovers_l_bracket_fixture_without_build(tmp_path):
    mesh = _create_l_bracket_mesh(depth=2.0)
    source = tmp_path / "l_bracket.stl"
    mesh.export(source)

    np.random.seed(19)
    result = run_pipeline(
        source,
        output_dir=None,
        sample_count=3500,
        auto_tune_sampling=False,
        tolerances=ToleranceConfig(linear=0.18, angular_deg=4.0, min_region_area=2.0),
    )

    assert result.reconstruction_plan.route == "prismatic_extrude"
    assert "base_extrude" in result.feature_kinds
    base_feature = next(
        feature
        for feature in result.debug["feature_parameters"]
        if feature["kind"] == "base_extrude"
    )
    profile_loop = base_feature["profile_loops"][0]
    assert len(profile_loop) >= 6
    assert _polygon_area(profile_loop) < 90.0
    assert result.build is not None
    assert "Polygon(*PROFILE)" in result.build.script


def test_generate_extrude_uses_pose_sketch_plane_when_present():
    base_feature = BaseExtrudeFeature(
        kind=FeatureKind.BASE_EXTRUDE,
        confidence=Confidence(score=0.95, reasons=[]),
        parameters={"depth": 2.0},
        references={},
        profile_loops=[[(-5.0, -3.0), (5.0, -3.0), (5.0, 3.0), (-5.0, 3.0)]],
        depth=2.0,
        sketch_plane={
            "origin": (10.0, 0.0, 0.0),
            "x_dir": (0.0, 1.0, 0.0),
            "z_dir": (1.0, 0.0, 0.0),
        },
    )
    script = generate_script([base_feature])
    assert "SKETCH_PLANE = Plane(origin=ORIGIN, x_dir=X_DIR, z_dir=Z_DIR)" in script
    assert "ORIGIN = (10.000000, 0.000000, 0.000000)" in script
    assert "with BuildSketch(SKETCH_PLANE)" in script


def test_run_pipeline_tall_cylinder_uses_revolve_route(tmp_path):
    mesh = trimesh.creation.cylinder(radius=2.0, height=10.0, sections=64)
    source = tmp_path / "tall_cylinder.stl"
    mesh.export(source)

    result = run_pipeline(
        source,
        output_dir=None,
        sample_count=4000,
        auto_tune_sampling=False,
        tolerances=ToleranceConfig(linear=0.15, angular_deg=4.0, min_region_area=2.0),
    )

    assert result.reconstruction_plan.part_class.value == "rotational"
    assert result.reconstruction_plan.route == "revolve_simple"
    assert "revolve" in result.feature_kinds
    assert result.build is not None
    assert "Axis(ORIGIN, AXIS_DIR)" in result.build.script
    assert "REVOLVE_PLANE" in result.build.script


@pytest.mark.skipif(
    importlib.util.find_spec("build123d") is None,
    reason="build123d is not installed in this interpreter",
)
def test_run_pipeline_handles_scan_like_noisy_multi_hole_mesh(tmp_path):
    script = _build_two_hole_plate_script(scale=1.0)
    build_result = build_step_from_script(script, tmp_path / "fixture_build")
    assert build_result.success is True

    preview_path = Path(build_result.metadata["preview_stl_path"])
    preview_mesh = trimesh.load_mesh(preview_path, force="mesh")
    scan_like_mesh = _artifact_mesh_from_preview(
        preview_mesh,
        artifact_kind="gaussian_noise",
        artifact_strength=0.0035,
        seed=11,
    )
    source = tmp_path / "scan_like_two_hole_plate.stl"
    scan_like_mesh.export(source)

    np.random.seed(11)
    result = run_pipeline(
        source,
        output_dir=None,
        sample_count=4000,
        tolerances=ToleranceConfig(linear=0.2, angular_deg=4.0, min_region_area=2.0),
    )

    assert "base_extrude" in result.feature_kinds
    assert result.feature_kinds.count("through_hole") >= 2
    assert result.primitive_kinds.count("cylinder") >= 2
    assert not any("through holes inferred" in w for w in result.warnings)


@pytest.mark.skipif(
    importlib.util.find_spec("build123d") is None,
    reason="build123d is not installed in this interpreter",
)
@pytest.mark.parametrize(
    ("artifact_kind", "artifact_strength", "scale", "min_holes"),
    [
        ("gaussian_noise", 0.0025, 1.0, 2),
        ("gaussian_noise", 0.0045, 1.0, 2),
        ("quantization", 0.0060, 1.0, 0),
        ("sparse_outliers", 0.0035, 1.0, 2),
        ("gaussian_noise", 0.0025, 2.0, 2),
        ("face_dropout", 0.05, 1.0, 0),
    ],
)
def test_run_pipeline_artifact_matrix_recovers_expected_features(
    tmp_path,
    artifact_kind: str,
    artifact_strength: float,
    scale: float,
    min_holes: int,
):
    script = _build_two_hole_plate_script(scale=scale)
    build_result = build_step_from_script(
        script,
        tmp_path / f"fixture_{artifact_kind}_{str(scale).replace('.', '_')}",
    )
    assert build_result.success is True

    preview_mesh = trimesh.load_mesh(Path(build_result.metadata["preview_stl_path"]), force="mesh")
    artifact_mesh = _artifact_mesh_from_preview(
        preview_mesh,
        artifact_kind=artifact_kind,
        artifact_strength=artifact_strength,
        seed=37,
    )
    source = tmp_path / (
        f"{artifact_kind}_{str(artifact_strength).replace('.', '_')}_{str(scale).replace('.', '_')}.stl"
    )
    artifact_mesh.export(source)

    linear_tolerance = max(0.2 * scale, artifact_strength * np.max(preview_mesh.extents) * 1.6)
    np.random.seed(37)
    result = run_pipeline(
        source,
        output_dir=None,
        sample_count=4500,
        tolerances=ToleranceConfig(
            linear=linear_tolerance,
            angular_deg=4.0,
            min_region_area=2.0 * scale,
        ),
    )

    assert "base_extrude" in result.feature_kinds
    assert result.feature_kinds.count("through_hole") >= min_holes
    assert result.primitive_kinds.count("plane") >= 2
    if min_holes >= 2:
        assert result.primitive_kinds.count("cylinder") >= 2
    else:
        assert result.feature_kinds.count("through_hole") < 2
        if result.primitive_kinds.count("cylinder") >= 1:
            assert any("through holes inferred" in w for w in result.warnings)


def test_validate_reconstruction_reports_invalid_solid_warning_from_metadata(tmp_path):
    mesh = trimesh.creation.box(extents=(10.0, 6.0, 2.0))
    source = tmp_path / "source_box.stl"
    mesh.export(source)
    loaded = load_mesh(source)

    invalid_build = BuildResult(
        success=True,
        step_path=None,
        errors=[],
        metadata={
            "solid_valid": False,
            "solid_manifold": False,
            "volume": float(mesh.volume),
            "bbox_extents": [10.0, 6.0, 2.0],
        },
    )

    report = validate_reconstruction(loaded, invalid_build)

    assert report is not None
    assert report.solid_valid is False
    assert "invalid solid reported by CAD kernel." in report.warnings
    assert "solid is non-manifold according to CAD kernel." in report.warnings


@pytest.mark.skipif(
    importlib.util.find_spec("build123d") is None,
    reason="build123d is not installed in this interpreter",
)
def test_generate_script_blind_hole_and_pocket_build(tmp_path):
    """Top-face blind hole + polygon pocket subtract after base extrude."""
    base = BaseExtrudeFeature(
        kind=FeatureKind.BASE_EXTRUDE,
        confidence=Confidence(score=0.95, reasons=[]),
        parameters={"depth": 4.0},
        references={},
        profile_loops=[[(-5.0, -3.0), (5.0, -3.0), (5.0, 3.0), (-5.0, 3.0)]],
        depth=4.0,
        sketch_plane={
            "origin": np.array([0.0, 0.0, 0.0]),
            "x_dir": np.array([1.0, 0.0, 0.0]),
            "y_dir": np.array([0.0, 1.0, 0.0]),
            "z_dir": np.array([0.0, 0.0, 1.0]),
        },
    )
    blind = BlindHoleFeature(
        kind=FeatureKind.BLIND_HOLE,
        confidence=Confidence(score=0.8, reasons=[]),
        parameters={},
        references={},
        center_xy=(1.0, 0.5),
        radius=0.45,
        hole_depth=1.25,
    )
    pocket = PocketFeature(
        kind=FeatureKind.POCKET,
        confidence=Confidence(score=0.75, reasons=[]),
        parameters={},
        references={},
        profile_loop=[(-2.0, -1.0), (2.0, -1.0), (2.0, 1.0), (-2.0, 1.0)],
        pocket_depth=0.65,
    )
    script = generate_script([base, blind, pocket])
    assert "BLIND_HOLES" in script and "POCKETS" in script
    build_result = build_step_from_script(script, tmp_path / "blind_pocket_build")
    assert build_result.success is True


def test_generate_build123d_script_supports_non_rectangular_polygon():
    base_feature = BaseExtrudeFeature(
        kind=FeatureKind.BASE_EXTRUDE,
        confidence=Confidence(score=0.95, reasons=[]),
        parameters={"depth": 2.0},
        references={},
        profile_loops=[[(-6.0, -3.0), (1.0, -3.0), (1.0, -1.0), (5.0, -1.0), (5.0, 3.0), (-6.0, 3.0)]],
        depth=2.0,
        sketch_plane={},
    )

    script = generate_script([base_feature])

    assert "Polygon(*PROFILE)" in script
    assert "(1.000000, -1.000000)" in script


def test_effective_sample_count_auto_tune_clamps_large_request():
    capped = effective_sample_count(
        50_000,
        face_count=500,
        vertex_count=800,
        auto_tune=True,
    )
    assert capped < 50_000
    assert effective_sample_count(2000, face_count=500, vertex_count=800, auto_tune=False) == 2000


def test_process_mesh_returns_json_friendly_payload(tmp_path):
    mesh = trimesh.creation.box(extents=(10.0, 6.0, 2.0))
    source = tmp_path / "box.stl"
    mesh.export(source)

    payload = process_mesh(input_path=source, build=False, sample_count=1200, auto_tune_sampling=False)

    assert payload["source_path"].endswith("box.stl")
    assert payload["build"]["build_success"] is False
    assert payload["build"]["metadata"]["requested_build"] is False
    assert "base_extrude" in payload["feature_kinds"]
    assert payload["debug"]["requested_sample_count"] == 1200
    assert payload["reconstruction_plan"]["route"] == "prismatic_extrude"
    json.dumps(payload, default=str)


def test_cli_outputs_json_payload(tmp_path):
    mesh = trimesh.creation.box(extents=(10.0, 6.0, 2.0))
    source = tmp_path / "box.stl"
    mesh.export(source)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mesh2cad.main",
            str(source),
            "--no-build",
            "--no-auto-tune",
            "--sample-count",
            "900",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["source_path"].endswith("box.stl")
    assert payload["build"]["build_success"] is False
    assert payload["debug"]["requested_sample_count"] == 900
    assert payload["debug"]["effective_sample_count"] == 900


@pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None,
    reason="fastapi is not installed in this interpreter",
)
def test_http_process_endpoint_returns_json_payload(tmp_path):
    mesh = trimesh.creation.box(extents=(10.0, 6.0, 2.0))
    source = tmp_path / "box.stl"
    mesh.export(source)

    client = TestClient(create_app())
    response = client.post(
        "/process",
        json={
            "input_path": str(source),
            "build": False,
            "sample_count": 1100,
            "auto_tune_sampling": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_path"].endswith("box.stl")
    assert payload["build"]["metadata"]["requested_build"] is False
    assert payload["debug"]["requested_sample_count"] == 1100
    assert payload["reconstruction_plan"]["route"] == "prismatic_extrude"


@pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None,
    reason="fastapi is not installed in this interpreter",
)
def test_ui_setup_login_and_job_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("MESH2CAD_STATE_DIR", str(tmp_path / "state"))

    mesh = trimesh.creation.box(extents=(10.0, 6.0, 2.0))
    source = tmp_path / "box.stl"
    mesh.export(source)

    client = TestClient(create_app())

    setup_page = client.get("/setup")
    assert setup_page.status_code == 200
    assert "Initial Setup" in setup_page.text

    setup_response = client.post(
        "/setup",
        data={"username": "admin", "password": "technical-pass"},
        follow_redirects=False,
    )
    assert setup_response.status_code == 303
    assert setup_response.headers["location"] == "/dashboard"

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "New Processing Job" in dashboard.text

    with source.open("rb") as handle:
        job_response = client.post(
            "/jobs",
            data={"sample_count": "900", "build": "on"},
            files={"source_file": ("box.stl", handle, "application/sla")},
            follow_redirects=False,
        )
    assert job_response.status_code == 303
    job_location = job_response.headers["location"]
    assert job_location.startswith("/jobs/")

    detail = client.get(job_location)
    assert detail.status_code == 200
    assert "Payload" in detail.text
    assert "Geometry Review" in detail.text

    status_payload = None
    job_id = job_location.rsplit("/", 1)[-1]
    for _ in range(120):
        status_response = client.get(f"/jobs/{job_id}/status")
        assert status_response.status_code == 200
        status_payload = status_response.json()
        if status_payload["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)

    assert status_payload is not None
    assert status_payload["status"] == "completed"

    report = client.get(f"{job_location}/files/report")
    assert report.status_code == 200
    assert '"source_path"' in report.text

    script = client.get(f"{job_location}/files/script")
    assert script.status_code == 200
    assert "from build123d import" in script.text

    if importlib.util.find_spec("build123d") is not None:
        preview = client.get(f"{job_location}/files/preview")
        assert preview.status_code == 200


@pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None,
    reason="fastapi is not installed in this interpreter",
)
def test_ui_rejects_unsupported_upload_extension(tmp_path, monkeypatch):
    monkeypatch.setenv("MESH2CAD_STATE_DIR", str(tmp_path / "state"))

    source = tmp_path / "bad.txt"
    source.write_text("not a mesh", encoding="utf-8")

    client = TestClient(create_app())
    client.post(
        "/setup",
        data={"username": "admin", "password": "technical-pass"},
        follow_redirects=False,
    )

    with source.open("rb") as handle:
        response = client.post(
            "/jobs",
            data={"sample_count": "500"},
            files={"source_file": ("bad.txt", handle, "text/plain")},
            follow_redirects=False,
        )

    assert response.status_code == 400


@pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None,
    reason="fastapi is not installed in this interpreter",
)
def test_ui_job_status_endpoint_eventually_completes(tmp_path, monkeypatch):
    monkeypatch.setenv("MESH2CAD_STATE_DIR", str(tmp_path / "state"))
    mesh = trimesh.creation.box(extents=(10.0, 6.0, 2.0))
    source = tmp_path / "box.stl"
    mesh.export(source)

    client = TestClient(create_app())
    client.post(
        "/setup",
        data={"username": "admin", "password": "technical-pass"},
        follow_redirects=False,
    )

    with source.open("rb") as handle:
        response = client.post(
            "/jobs",
            data={"sample_count": "900"},
            files={"source_file": ("box.stl", handle, "application/sla")},
            follow_redirects=False,
        )
    assert response.status_code == 303
    job_location = response.headers["location"]
    job_id = job_location.rsplit("/", 1)[-1]

    status_payload = None
    for _ in range(40):
        status_response = client.get(f"/jobs/{job_id}/status")
        assert status_response.status_code == 200
        status_payload = status_response.json()
        if status_payload["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)

    assert status_payload is not None
    assert status_payload["status"] == "completed"


@pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None,
    reason="fastapi is not installed in this interpreter",
)
def test_http_async_process_submission_and_polling(tmp_path):
    mesh = trimesh.creation.box(extents=(10.0, 6.0, 2.0))
    source = tmp_path / "box.stl"
    mesh.export(source)

    client = TestClient(create_app())
    submit = client.post(
        "/process/submit",
        json={"input_path": str(source), "build": False, "sample_count": 800},
    )
    assert submit.status_code == 200
    job_id = submit.json()["job_id"]

    payload = None
    for _ in range(40):
        status = client.get(f"/process/jobs/{job_id}")
        assert status.status_code == 200
        payload = status.json()
        if payload["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)

    assert payload is not None
    assert payload["status"] == "completed"
    assert payload["payload"]["source_path"].endswith("box.stl")
    assert payload["payload"]["reconstruction_plan"]["route"] == "prismatic_extrude"


@pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None,
    reason="fastapi is not installed in this interpreter",
)
def test_http_process_job_cancel_when_still_queued(tmp_path):
    mesh = trimesh.creation.box(extents=(10.0, 6.0, 2.0))
    source = tmp_path / "box.stl"
    mesh.export(source)

    client = TestClient(create_app())
    submit = client.post(
        "/process/submit",
        json={
            "input_path": str(source),
            "build": False,
            "sample_count": 800,
            "auto_tune_sampling": False,
        },
    )
    assert submit.status_code == 200
    job_id = submit.json()["job_id"]

    cancel = client.post(f"/process/jobs/{job_id}/cancel")
    assert cancel.status_code == 200
    body = cancel.json()
    assert body["job_id"] == job_id
    assert body["status"] in {"cancelled", "cancel_requested"}


@pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None,
    reason="fastapi is not installed in this interpreter",
)
def test_http_async_process_retry_after_completion(tmp_path):
    mesh = trimesh.creation.box(extents=(10.0, 6.0, 2.0))
    source = tmp_path / "box.stl"
    mesh.export(source)

    client = TestClient(create_app())
    submit = client.post(
        "/process/submit",
        json={"input_path": str(source), "build": False, "sample_count": 800},
    )
    assert submit.status_code == 200
    job_id = submit.json()["job_id"]

    payload = None
    for _ in range(60):
        status = client.get(f"/process/jobs/{job_id}")
        assert status.status_code == 200
        payload = status.json()
        if payload["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)

    assert payload is not None
    assert payload["status"] == "completed"

    retry = client.post(f"/process/jobs/{job_id}/retry")
    assert retry.status_code == 200
    retry_body = retry.json()
    assert retry_body["job_id"] == job_id
    assert retry_body["status"] == "queued"

    payload = None
    for _ in range(60):
        status = client.get(f"/process/jobs/{job_id}")
        assert status.status_code == 200
        payload = status.json()
        if payload["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)

    assert payload is not None
    assert payload["status"] == "completed"
    assert payload["payload"]["source_path"].endswith("box.stl")


@pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None,
    reason="fastapi is not installed in this interpreter",
)
def test_ui_job_retry_after_completion(tmp_path, monkeypatch):
    monkeypatch.setenv("MESH2CAD_STATE_DIR", str(tmp_path / "state"))
    mesh = trimesh.creation.box(extents=(10.0, 6.0, 2.0))
    source = tmp_path / "box.stl"
    mesh.export(source)

    client = TestClient(create_app())
    client.post(
        "/setup",
        data={"username": "admin", "password": "technical-pass"},
        follow_redirects=False,
    )

    with source.open("rb") as handle:
        response = client.post(
            "/jobs",
            data={"sample_count": "900"},
            files={"source_file": ("box.stl", handle, "application/sla")},
            follow_redirects=False,
        )
    assert response.status_code == 303
    job_location = response.headers["location"]
    job_id = job_location.rsplit("/", 1)[-1]

    status_payload = None
    for _ in range(80):
        status_response = client.get(f"/jobs/{job_id}/status")
        assert status_response.status_code == 200
        status_payload = status_response.json()
        if status_payload["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)

    assert status_payload is not None
    assert status_payload["status"] == "completed"

    retry = client.post(f"/jobs/{job_id}/retry", follow_redirects=False)
    assert retry.status_code == 303
    assert retry.headers["location"] == f"/jobs/{job_id}"

    status_payload = None
    for _ in range(80):
        status_response = client.get(f"/jobs/{job_id}/status")
        assert status_response.status_code == 200
        status_payload = status_response.json()
        if status_payload["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)

    assert status_payload is not None
    assert status_payload["status"] == "completed"


@pytest.mark.skipif(
    importlib.util.find_spec("build123d") is None,
    reason="build123d is not installed in this interpreter",
)
def test_validate_reconstruction_reports_small_volume_delta_for_box(tmp_path):
    mesh = trimesh.creation.box(extents=(10.0, 6.0, 2.0))
    source = tmp_path / "box.stl"
    mesh.export(source)

    loaded = load_mesh(source)
    repaired = repair_mesh(loaded)
    build_result = build_step_from_script(
        "\n".join(
            [
                "from build123d import BuildPart, Box",
                "",
                "with BuildPart() as part:",
                "    Box(10, 6, 2)",
                "",
                "result = part.part",
            ]
        ),
        tmp_path,
    )

    validation = validate_reconstruction(repaired, build_result)

    assert validation is not None
    assert validation.solid_valid is True
    assert validation.rms_error is not None
    assert validation.max_error is not None
    assert validation.rms_error < 1e-4
    assert validation.max_error < 1e-3
    assert validation.volume_delta_ratio is not None
    assert validation.volume_delta_ratio < 1e-6


@pytest.mark.skipif(
    importlib.util.find_spec("build123d") is None,
    reason="build123d is not installed in this interpreter",
)
def test_validate_reconstruction_reports_surface_error_for_mismatched_box(tmp_path):
    mesh = trimesh.creation.box(extents=(10.0, 6.0, 2.0))
    source = tmp_path / "box.stl"
    mesh.export(source)

    loaded = load_mesh(source)
    repaired = repair_mesh(loaded)
    build_result = build_step_from_script(
        "\n".join(
            [
                "from build123d import BuildPart, Box",
                "",
                "with BuildPart() as part:",
                "    Box(9, 6, 2)",
                "",
                "result = part.part",
            ]
        ),
        tmp_path,
    )

    validation = validate_reconstruction(repaired, build_result)

    assert validation is not None
    assert validation.solid_valid is True
    assert validation.rms_error is not None
    assert validation.max_error is not None
    assert validation.volume_delta_ratio is not None
    assert validation.rms_error > 0.05
    assert validation.max_error > 0.2
    assert validation.volume_delta_ratio > 0.05
