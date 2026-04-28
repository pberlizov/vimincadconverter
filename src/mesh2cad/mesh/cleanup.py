from __future__ import annotations

from dataclasses import replace

import numpy as np
import trimesh

from mesh2cad.mesh.io import MeshData


def repair_mesh(mesh_data: MeshData, *, component_index: int | None = None) -> MeshData:
    """Apply conservative repairs that help downstream analysis without reshaping parts.

    When the mesh has multiple connected components, the largest component by surface area
    is kept by default. Pass ``component_index`` to keep the N-th largest instead (0-based),
    which is useful for multi-body STEP/STL imports where a smaller body should be analyzed.
    """
    mesh = mesh_data.mesh.copy()

    mesh.remove_unreferenced_vertices()
    nondegenerate = mesh.nondegenerate_faces()
    if nondegenerate is not None:
        mesh.update_faces(nondegenerate)

    unique_faces = mesh.unique_faces()
    if unique_faces is not None:
        mesh.update_faces(unique_faces)

    mesh.remove_unreferenced_vertices()
    mesh.remove_infinite_values()
    mesh.process(validate=True)

    components = mesh.split(only_watertight=False)
    if len(components) > 1:
        ranked = sorted(components, key=lambda comp: comp.area, reverse=True)
        idx = 0 if component_index is None else int(component_index)
        if idx < 0 or idx >= len(ranked):
            idx = 0
        mesh = ranked[idx]

    trimesh.repair.fix_normals(mesh, multibody=True)
    trimesh.repair.fix_inversion(mesh, multibody=True)

    vertex_normals = None
    if mesh.vertex_normals is not None and len(mesh.vertex_normals) == len(mesh.vertices):
        vertex_normals = np.asarray(mesh.vertex_normals, dtype=np.float64)

    return replace(
        mesh_data,
        mesh=mesh,
        vertices=np.asarray(mesh.vertices, dtype=np.float64),
        faces=np.asarray(mesh.faces, dtype=np.int64),
        vertex_normals=vertex_normals,
    )


def simplify_mesh(mesh_data: MeshData, target_faces: int) -> MeshData:
    """Reduce face count to improve performance while preserving overall shape."""
    if target_faces <= 0:
        raise ValueError("target_faces must be positive")

    mesh = mesh_data.mesh.copy()
    if len(mesh.faces) <= target_faces:
        return mesh_data

    simplified = mesh.simplify_quadric_decimation(face_count=target_faces)
    vertex_normals = None
    if simplified.vertex_normals is not None and len(simplified.vertex_normals) == len(simplified.vertices):
        vertex_normals = np.asarray(simplified.vertex_normals, dtype=np.float64)

    return replace(
        mesh_data,
        mesh=simplified,
        vertices=np.asarray(simplified.vertices, dtype=np.float64),
        faces=np.asarray(simplified.faces, dtype=np.int64),
        vertex_normals=vertex_normals,
    )
