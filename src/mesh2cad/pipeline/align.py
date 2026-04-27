from __future__ import annotations

import numpy as np
import trimesh


def icp_align_preview_to_source(
    preview: trimesh.Trimesh,
    source: trimesh.Trimesh,
    *,
    samples: int = 800,
    iterations: int = 10,
    seed: int = 0,
) -> trimesh.Trimesh:
    """Rigidly align ``preview`` toward ``source`` using point-to-plane ICP with naive closest points (no rtree)."""
    _ = seed  # reserved for deterministic surface sampling when upstream adds RNG hooks
    if len(preview.faces) == 0 or len(source.faces) == 0:
        return preview.copy()

    moving = preview.copy()
    sample_cap = min(int(samples), 4000, max(1, len(moving.faces) * 4))
    for _ in range(max(1, int(iterations))):
        P, _ = trimesh.sample.sample_surface(moving, sample_cap)
        try:
            closest, _dist, _fid = trimesh.proximity.closest_point_naive(source, P)
        except Exception:
            break
        Q = np.asarray(closest, dtype=np.float64)
        P = np.asarray(P, dtype=np.float64)
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
