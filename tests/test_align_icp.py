"""Tests for preview→source ICP, including auxiliary scan targets."""

from __future__ import annotations

import numpy as np
import trimesh

from mesh2cad.pipeline.align import icp_align_preview_to_source


def _mean_nn_distance(query: np.ndarray, target: np.ndarray) -> float:
    from scipy.spatial import cKDTree

    tree = cKDTree(np.asarray(target, dtype=np.float64))
    d, _ = tree.query(np.asarray(query, dtype=np.float64))
    return float(np.mean(d))


def test_icp_with_auxiliary_scan_points_pulls_preview_toward_cloud():
    true_shape = trimesh.creation.box(extents=(4.0, 3.0, 2.0))
    scan_pts, _ = trimesh.sample.sample_surface(true_shape, 1200)
    scan_pts = np.asarray(scan_pts, dtype=np.float64) + np.array([1.5, -0.4, 0.2], dtype=np.float64)

    preview = true_shape.copy()
    wrong = preview.copy()
    wrong.apply_translation([2.0, -1.0, 0.5])

    hull = true_shape.convex_hull
    aligned = icp_align_preview_to_source(
        wrong,
        hull,
        samples=900,
        iterations=15,
        seed=42,
        icp_target_points=scan_pts,
    )

    q_wrong, _ = trimesh.sample.sample_surface(wrong, 600)
    q_aligned, _ = trimesh.sample.sample_surface(aligned, 600)
    assert _mean_nn_distance(q_aligned, scan_pts) < 0.85 * _mean_nn_distance(q_wrong, scan_pts)


def test_icp_mesh_target_matches_previous_behavior():
    mesh = trimesh.creation.cylinder(radius=1.0, height=4.0, sections=32)
    shifted = mesh.copy()
    shifted.apply_translation([0.3, 0.0, 0.0])

    aligned = icp_align_preview_to_source(
        shifted,
        mesh,
        samples=600,
        iterations=12,
        seed=1,
        icp_target_points=None,
    )

    q_src, _ = trimesh.sample.sample_surface(mesh, 400)
    q_al, _ = trimesh.sample.sample_surface(aligned, 400)
    assert _mean_nn_distance(q_al, q_src) < 0.2
