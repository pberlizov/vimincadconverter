"""Optional Open3D-backed point-to-mesh distances (used when explicitly enabled)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import trimesh


def point_to_mesh_distances_open3d(
    points: np.ndarray,
    mesh: trimesh.Trimesh,
) -> np.ndarray | None:
    """Return per-point distances to the triangle mesh, or ``None`` if Open3d is unavailable."""
    try:
        import open3d as o3d
        import open3d.core as o3c
    except ImportError:
        return None

    try:
        vertices = np.asarray(mesh.vertices, dtype=np.float64)
        faces = np.asarray(mesh.faces, dtype=np.int64)
        if vertices.size == 0 or faces.size == 0:
            return None

        legacy = o3d.geometry.TriangleMesh(
            o3d.utility.Vector3dVector(vertices),
            o3d.utility.Vector3iVector(faces.astype(np.int32)),
        )
        legacy.remove_duplicated_vertices()
        legacy.remove_degenerate_triangles()
        legacy.remove_duplicated_triangles()
        legacy.remove_unreferenced_vertices()
        legacy.compute_vertex_normals()

        mesh_t = o3d.t.geometry.TriangleMesh.from_legacy(legacy)
        scene = o3d.t.geometry.RaycastingScene()
        scene.add_triangles(mesh_t)

        pts = np.asarray(points, dtype=np.float32)
        query = o3c.Tensor(pts)
        if hasattr(scene, "compute_distance"):
            distances = scene.compute_distance(query)
        else:  # pragma: no cover - version-specific
            return None

        out = np.asarray(distances.numpy(), dtype=np.float64).reshape(-1)
        if out.shape[0] != pts.shape[0]:
            return None
        return out
    except Exception:
        return None
