from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import cKDTree


def estimate_point_normals_knn(
    points: NDArray[np.float64],
    *,
    k: int = 12,
) -> NDArray[np.float64]:
    """Estimate normals for an unoriented point cloud via local PCA (k nearest neighbors)."""
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) < max(4, k):
        out = np.zeros_like(pts)
        out[:, 2] = 1.0
        return out

    k_eff = min(int(k), len(pts) - 1)
    tree = cKDTree(pts)
    _, indices = tree.query(pts, k=k_eff + 1)
    normals = np.zeros_like(pts)
    for row_index, neighbor_indices in enumerate(indices):
        neighbors = pts[neighbor_indices[1:]]
        centered = neighbors - neighbors.mean(axis=0)
        _, _, vt = np.linalg.svd(centered, full_matrices=False)
        normal = vt[-1, :]
        nrm = float(np.linalg.norm(normal))
        normals[row_index] = (normal / nrm) if nrm > 1e-12 else np.array([0.0, 0.0, 1.0], dtype=np.float64)

    flip_toward_camera = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    if float(np.mean(normals @ flip_toward_camera)) < 0.0:
        normals *= -1.0
    return normals
