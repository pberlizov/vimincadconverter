from __future__ import annotations

import numpy as np
import trimesh
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from mesh2cad.mesh.point_normals import estimate_point_normals_knn


def icp_align_preview_to_source(
    preview: trimesh.Trimesh,
    source: trimesh.Trimesh,
    *,
    samples: int = 800,
    iterations: int = 10,
    seed: int = 0,
    icp_target_points: np.ndarray | None = None,
) -> trimesh.Trimesh:
    """Rigidly align ``preview`` toward ``source`` using trimmed correspondences.

    Later iterations use a **point-to-plane** linearized step when normals are available;
    earlier iterations and fallbacks use **point-to-point** (SVD / Kabsch). Correspondence
    outliers are trimmed by distance percentile each iteration.
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
    target_normals: np.ndarray | None = None
    if icp_target_points is not None:
        pts = np.asarray(icp_target_points, dtype=np.float64).reshape(-1, 3)
        if len(pts) >= 6:
            max_pts = 50_000
            if len(pts) > max_pts:
                idx = rng.choice(len(pts), size=max_pts, replace=False)
                pts = pts[idx]
            target_cloud = pts
            target_tree = cKDTree(pts)
            target_normals = estimate_point_normals_knn(pts, k=min(16, max(4, len(pts) - 1)))

    n_iter = max(1, int(iterations))
    pt_plane_start = max(0, int(0.45 * n_iter))

    for iteration in range(n_iter):
        P, _fid_p = trimesh.sample.sample_surface(moving, sample_cap)
        P = np.asarray(P, dtype=np.float64)

        if target_tree is not None and target_cloud is not None and target_normals is not None:
            _, nn = target_tree.query(P)
            nn = np.asarray(nn, dtype=np.intp)
            Q = target_cloud[nn]
            n_q = target_normals[nn]
        else:
            try:
                closest, _dist, tri_ids = trimesh.proximity.closest_point_naive(source, P)
            except Exception:
                break
            Q = np.asarray(closest, dtype=np.float64)
            tri_ids = np.asarray(tri_ids, dtype=np.intp)
            n_q = np.asarray(source.face_normals[tri_ids], dtype=np.float64)

        if len(P) < 6:
            break

        P, Q, n_q = _trim_correspondences(P, Q, n_q, percentile=88.0)
        if len(P) < 6:
            break

        use_pt_plane = iteration >= pt_plane_start
        if use_pt_plane:
            omega, t = _point_to_plane_delta(P, Q, n_q, damping=0.85)
            if omega is None or not np.all(np.isfinite(omega)) or not np.all(np.isfinite(t)):
                R, t_k = _kabsch(P, Q)
                delta = _delta_from_Rt(R, t_k)
            else:
                delta = _delta_from_omega_t(omega, t)
        else:
            R, t_k = _kabsch(P, Q)
            delta = _delta_from_Rt(R, t_k)

        moving.apply_transform(delta)

    return moving


def _trim_correspondences(
    P: np.ndarray,
    Q: np.ndarray,
    n_q: np.ndarray,
    *,
    percentile: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    d = np.linalg.norm(P - Q, axis=1)
    thr = float(np.percentile(d, percentile))
    mask = d <= thr
    if int(np.sum(mask)) < 6:
        return P, Q, n_q
    return P[mask], Q[mask], n_q[mask]


def _kabsch(P: np.ndarray, Q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
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
    return R, t


def _delta_from_Rt(R: np.ndarray, t: np.ndarray) -> np.ndarray:
    delta = np.eye(4, dtype=np.float64)
    delta[:3, :3] = R
    delta[:3, 3] = t
    return delta


def _point_to_plane_delta(
    P: np.ndarray,
    Q: np.ndarray,
    n: np.ndarray,
    *,
    damping: float,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Linearized point-to-plane: minimize sum (n_i·(R p_i + t - q_i))^2 for small rotation."""
    M = np.zeros((6, 6), dtype=np.float64)
    b = np.zeros(6, dtype=np.float64)
    for i in range(len(P)):
        p, q, ni = P[i], Q[i], n[i]
        ci = np.concatenate([np.cross(p, ni), ni])
        di = float(np.dot(ni, q - p))
        M += np.outer(ci, ci)
        b += ci * di
    try:
        xi = np.linalg.solve(M, b)
    except np.linalg.LinAlgError:
        xi, *_ = np.linalg.lstsq(M, b, rcond=1e-9)
    if not np.all(np.isfinite(xi)):
        return None, None
    omega = xi[:3] * float(damping)
    t = xi[3:6] * float(damping)
    return omega, t


def _delta_from_omega_t(omega: np.ndarray, t: np.ndarray) -> np.ndarray:
    angle = float(np.linalg.norm(omega))
    if angle < 1e-12:
        R = np.eye(3, dtype=np.float64)
    else:
        R = Rotation.from_rotvec(omega).as_matrix()
    return _delta_from_Rt(R, t)
