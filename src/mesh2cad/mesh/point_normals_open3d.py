"""Optional Open3D normal estimation for large point clouds."""

from __future__ import annotations

import os

import numpy as np
from numpy.typing import NDArray


def _use_open3d_cloud() -> bool:
    return os.environ.get("MESH2CAD_USE_OPEN3D_CLOUD", "").strip().lower() in {"1", "true", "yes", "on"}


def _min_points() -> int:
    try:
        return max(5_000, int(os.environ.get("MESH2CAD_OPEN3D_CLOUD_MIN_POINTS", "50000")))
    except ValueError:
        return 50_000


def estimate_point_normals_open3d(
    points: NDArray[np.float64],
    *,
    k: int = 12,
) -> NDArray[np.float64] | None:
    """Return Open3D-estimated normals, or ``None`` if disabled / unavailable / too small."""
    if not _use_open3d_cloud():
        return None
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) < _min_points():
        return None
    try:
        import open3d as o3d
    except ImportError:
        return None

    try:
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(pts)
        k_eff = min(int(k), max(3, len(pts) - 1))
        pcd.estimate_normals(
            search_param=o3d.geometry.KDTreeSearchParamKNN(knn=k_eff),
        )
        normals = np.asarray(pcd.normals, dtype=np.float64)
        flip_toward_camera = np.array([0.0, 0.0, 1.0], dtype=np.float64)
        if float(np.mean(normals @ flip_toward_camera)) < 0.0:
            normals *= -1.0
        return normals
    except Exception:
        return None
