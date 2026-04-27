"""Unit tests for planar pocket inference (interior parallel faces)."""

from __future__ import annotations

import numpy as np

from mesh2cad.domain.primitives import PlanePrimitive, PrimitiveRegion
from mesh2cad.domain.types import Confidence, PrimitiveKind, ToleranceConfig
from mesh2cad.mesh.sampling import SampledCloud


def _make_stack_cloud_and_planes():
    """Thin plate z in [-1,1] with two small interior horizontal patches forming a void."""
    tol = ToleranceConfig(linear=0.15, angular_deg=3.0, min_region_area=0.5)
    pts: list[list[float]] = []
    # large bottom / top caps (sparse)
    for x in np.linspace(-4.5, 4.5, 10):
        for y in np.linspace(-2.5, 2.5, 6):
            pts.append([x, y, -1.0])
            pts.append([x, y, 1.0])
    # pocket floor z=-0.35, ceiling z=0.35, small XY patch
    for x in np.linspace(-0.9, 0.9, 5):
        for y in np.linspace(-0.9, 0.9, 5):
            pts.append([x, y, -0.35])
            pts.append([x, y, 0.35])
    points = np.asarray(pts, dtype=np.float64)
    normals = np.zeros_like(points)
    normals[:, 2] = 1.0
    cloud = SampledCloud(points=points, normals=normals, source_face_indices=None)

    n = len(points)
    bottom_idx = list(range(0, 120, 2))
    top_idx = list(range(1, 120, 2))
    pocket_lo = 120
    pocket_hi = n
    pocket_a = list(range(pocket_lo, pocket_lo + 25))
    pocket_b = list(range(pocket_lo + 25, pocket_hi))

    bottom = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.95, reasons=[]),
        region=PrimitiveRegion(point_indices=bottom_idx, area=55.0),
        origin=np.array([0.0, 0.0, -1.0]),
        normal=np.array([0.0, 0.0, 1.0]),
    )
    top = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.95, reasons=[]),
        region=PrimitiveRegion(point_indices=top_idx, area=55.0),
        origin=np.array([0.0, 0.0, 1.0]),
        normal=np.array([0.0, 0.0, -1.0]),
    )
    pf = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.7, reasons=[]),
        region=PrimitiveRegion(point_indices=pocket_a, area=2.5),
        origin=np.array([0.0, 0.0, -0.35]),
        normal=np.array([0.0, 0.0, 1.0]),
    )
    pc = PlanePrimitive(
        kind=PrimitiveKind.PLANE,
        confidence=Confidence(score=0.7, reasons=[]),
        region=PrimitiveRegion(point_indices=pocket_b, area=2.5),
        origin=np.array([0.0, 0.0, 0.35]),
        normal=np.array([0.0, 0.0, -1.0]),
    )
    planes = [bottom, top, pf, pc]
    return cloud, planes, tol


def test_infer_planar_pockets_detects_interior_void():
    import mesh2cad.pipeline.infer_features as inf

    cloud, planes, tol = _make_stack_cloud_and_planes()
    base = inf._infer_base_extrude(planes, cloud, tol)
    assert base is not None
    pockets = inf._infer_planar_pockets(planes, base, cloud, tol)
    assert len(pockets) >= 1
    assert pockets[0].pocket_depth > 0.4
    assert len(pockets[0].profile_loop) >= 3
