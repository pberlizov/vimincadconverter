from __future__ import annotations

import numpy as np
import trimesh
from scipy.spatial import cKDTree


def icp_align_preview_to_source(
    preview: trimesh.Trimesh,
    source: trimesh.Trimesh,
    *,
    samples: int = 800,
    iterations: int = 10,
    seed: int = 0,
    icp_target_points: np.ndarray | None = None,
) -> trimesh.Trimesh:
    """Rigidly align ``preview`` toward ``source`` using SVD rigid steps per iteration.

    By default, correspondences ``Q`` are closest points on the ``source`` triangle mesh.
    When ``icp_target_points`` is set (e.g. raw scan samples), ``Q`` is the nearest neighbor
    in that cloud so ICP can align to dense points instead of a convex-hull proxy mesh.
    """
    rng = np.random.default_rng(int(seed) & 0xFFFF_FFFF)
    if len(preview.faces) == 0:
        return preview.copy()
    if icp_target_points is None and len(source.faces) == 0:
        return preview.copy()

    moving = preview.copy()
    sample_cap = min(int(samples), 4000, max(1, len(moving.faces) * 4))

    target_cloud: np.ndarray | None = None
    target_tree: cKDTree | None = None
    if icp_target_points is not None:
        pts = np.asarray(icp_target_points, dtype=np.float64).reshape(-1, 3)
        if len(pts) >= 6:
            max_pts = 50_000
            if len(pts) > max_pts:
                idx = rng.choice(len(pts), size=max_pts, replace=False)
                pts = pts[idx]
            target_cloud = pts
            target_tree = cKDTree(pts)

    for _ in range(max(1, int(iterations))):
        P, _ = trimesh.sample.sample_surface(moving, sample_cap)
        P = np.asarray(P, dtype=np.float64)
        if target_tree is not None and target_cloud is not None:
            _, nn = target_tree.query(P)
            Q = target_cloud[np.asarray(nn, dtype=np.intp)]
        else:
            try:
                closest, _dist, _fid = trimesh.proximity.closest_point_naive(source, P)
            except Exception:
                break
            Q = np.asarray(closest, dtype=np.float64)
        if len(P) < 6:
            break
        mu_p = P.mean(axis=0)
        mu_q = Q.mean(axis=0)
        Pc = P - mu_p
        Qc = Q - mu_q
        H = Pc.T @ Qc
        U, _, Vt = np.linalg.svd(H)
        R = Vt.T @ U.T
        if float(np.linalg.det(R)) < 0.0:
            Vt_adj = Vt.copy()
            Vt_adj[-1, :] *= -1.0
            R = Vt_adj.T @ U.T
        t = mu_q - R @ mu_p
        delta = np.eye(4, dtype=np.float64)
        delta[:3, :3] = R
        delta[:3, 3] = t
        moving.apply_transform(delta)
    return moving
