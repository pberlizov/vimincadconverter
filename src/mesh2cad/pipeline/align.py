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
    hybrid_hull_weight: float = 0.0,
) -> trimesh.Trimesh:
    """Rigidly align ``preview`` toward ``source`` using trimmed correspondences.

    Later iterations use a **point-to-plane** linearized step when normals are available;
    earlier iterations and fallbacks use **point-to-point** (SVD / Kabsch). Correspondence
    outliers are trimmed with **percentile + MAD** gates.

    When ``icp_target_points`` is set and ``hybrid_hull_weight`` in ``(0, 1]``, targets ``Q``
    and normals blend the scan NN with the **hull mesh** closest points so ICP is anchored
    to both dense samples and the watertight proxy.
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
    w_hull = float(np.clip(hybrid_hull_weight, 0.0, 1.0))
    use_hybrid = (
        w_hull > 1e-6
        and target_tree is not None
        and target_cloud is not None
        and target_normals is not None
        and len(source.faces) > 0
    )

    for iteration in range(n_iter):
        P, _fid_p = trimesh.sample.sample_surface(moving, sample_cap)
        P = np.asarray(P, dtype=np.float64)

        if target_tree is not None and target_cloud is not None and target_normals is not None:
            _, nn = target_tree.query(P)
            nn = np.asarray(nn, dtype=np.intp)
            Q_c = target_cloud[nn]
            n_c = target_normals[nn]
            if use_hybrid:
                try:
                    closest_h, _dh, tri_h = trimesh.proximity.closest_point_naive(source, P)
                    Q_h = np.asarray(closest_h, dtype=np.float64)
                    tri_h = np.asarray(tri_h, dtype=np.intp)
                    n_h = np.asarray(source.face_normals[tri_h], dtype=np.float64)
                except Exception:
                    Q, n_q = Q_c, n_c
                else:
                    w = w_hull
                    Q = (1.0 - w) * Q_c + w * Q_h
                    n_q = _normalize_rows((1.0 - w) * n_c + w * n_h)
            else:
                Q, n_q = Q_c, n_c
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

        pct = 82.0 if iteration < max(1, n_iter // 3) else 90.0
        P, Q, n_q = _trim_correspondences(P, Q, n_q, percentile=pct, mad_sigma=3.5)
        if len(P) < 6:
            break

        use_pt_plane = iteration >= pt_plane_start
        if use_pt_plane:
            damp = 0.62 + 0.28 * float(iteration + 1) / float(n_iter)
            damp = float(np.clip(damp, 0.62, 0.95))
            omega, t = _point_to_plane_delta(P, Q, n_q, damping=damp)
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


def _normalize_rows(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=1, keepdims=True)
    n = np.maximum(n, 1e-12)
    return v / n


def _trim_correspondences(
    P: np.ndarray,
    Q: np.ndarray,
    n_q: np.ndarray,
    *,
    percentile: float,
    mad_sigma: float = 3.5,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    d = np.linalg.norm(P - Q, axis=1)
    thr_p = float(np.percentile(d, percentile))
    mask = d <= thr_p
    if mad_sigma > 0.0:
        med = float(np.median(d))
        mad = float(np.median(np.abs(d - med))) + 1e-9
        thr_m = med + float(mad_sigma) * 1.4826 * mad
        mask = mask & (d <= thr_m)
    n_keep = int(np.sum(mask))
    if n_keep < 6:
        mask_p = d <= thr_p
        if int(np.sum(mask_p)) >= 6:
            return P[mask_p], Q[mask_p], n_q[mask_p]
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
        xi, *_ = np.linalg.lstsq(M, b, rcond=1e-10)
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
