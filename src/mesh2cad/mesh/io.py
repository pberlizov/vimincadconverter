from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from numpy.typing import NDArray

from mesh2cad.exceptions import MeshLoadError


@dataclass(slots=True)
class MeshData:
    mesh: trimesh.Trimesh
    vertices: NDArray[np.float64]
    faces: NDArray[np.int64]
    vertex_normals: NDArray[np.float64] | None
    units: str | None
    source_path: Path
    auxiliary_surface_points: NDArray[np.float64] | None = field(
        default=None,
        metadata={"description": "Original scan points when the input was a point cloud."},
    )


def load_mesh(path: str | Path) -> MeshData:
    """Load a mesh file and normalize it to a single Trimesh instance."""
    try:
        source_path = Path(path).expanduser().resolve()
        
        # Validate file exists and is readable
        if not source_path.exists():
            raise MeshLoadError(
                f"File not found: {source_path}",
                details={"path": str(source_path), "error_type": "file_not_found"}
            )
        
        if not source_path.is_file():
            raise MeshLoadError(
                f"Path is not a file: {source_path}",
                details={"path": str(source_path), "error_type": "not_a_file"}
            )
        
        # Check file size (prevent extremely large files)
        file_size_mb = source_path.stat().st_size / (1024 * 1024)
        if file_size_mb > 1000:  # 1GB limit
            raise MeshLoadError(
                f"File too large: {file_size_mb:.1f}MB (limit: 1000MB)",
                details={
                    "path": str(source_path), 
                    "size_mb": file_size_mb,
                    "error_type": "file_too_large"
                }
            )
        
        # Validate file extension
        supported_extensions = {".stl", ".obj", ".ply"}
        if source_path.suffix.lower() not in supported_extensions:
            raise MeshLoadError(
                f"Unsupported file extension: {source_path.suffix}",
                details={
                    "path": str(source_path),
                    "extension": source_path.suffix,
                    "supported": list(supported_extensions),
                    "error_type": "unsupported_extension"
                }
            )
        
        # Attempt to load the mesh
        try:
            loaded = trimesh.load(source_path, force="mesh")
        except Exception as e:
            raise MeshLoadError(
                f"Failed to load mesh file: {e}",
                details={
                    "path": str(source_path),
                    "original_error": str(e),
                    "error_type": "load_failure"
                }
            ) from e

        # Handle different geometry types
        if isinstance(loaded, trimesh.Scene):
            try:
                meshes = tuple(
                    geometry
                    for geometry in loaded.geometry.values()
                    if isinstance(geometry, trimesh.Trimesh)
                )
                if not meshes:
                    raise MeshLoadError(
                        "Scene contains no mesh geometry",
                        details={
                            "path": str(source_path),
                            "geometry_types": [type(g).__name__ for g in loaded.geometry.values()],
                            "error_type": "no_mesh_in_scene"
                        }
                    )
                mesh = trimesh.util.concatenate(meshes)
            except Exception as e:
                raise MeshLoadError(
                    f"Failed to concatenate scene geometry: {e}",
                    details={
                        "path": str(source_path),
                        "original_error": str(e),
                        "error_type": "concatenation_failure"
                    }
                ) from e
        elif isinstance(loaded, trimesh.Trimesh):
            mesh = loaded
        else:
            raise MeshLoadError(
                f"Unsupported geometry type: {type(loaded)!r}",
                details={
                    "path": str(source_path),
                    "geometry_type": type(loaded).__name__,
                    "error_type": "unsupported_geometry"
                }
            )

        # Validate mesh content
        if mesh.vertices.size == 0:
            raise MeshLoadError(
                "Mesh has no vertices",
                details={
                    "path": str(source_path),
                    "vertices_count": 0,
                    "error_type": "empty_vertices"
                }
            )
        
        if mesh.faces.size == 0:
            raise MeshLoadError(
                "Mesh has no faces",
                details={
                    "path": str(source_path),
                    "faces_count": 0,
                    "error_type": "empty_faces"
                }
            )

        # Handle vertex normals
        try:
            if mesh.vertex_normals is None or len(mesh.vertex_normals) != len(mesh.vertices):
                vertex_normals = None
            else:
                vertex_normals = np.asarray(mesh.vertex_normals, dtype=np.float64)
        except Exception as e:
            vertex_normals = None  # Non-critical, continue without normals

        return MeshData(
            mesh=mesh,
            vertices=np.asarray(mesh.vertices, dtype=np.float64),
            faces=np.asarray(mesh.faces, dtype=np.int64),
            vertex_normals=vertex_normals,
            units=getattr(mesh, "units", None),
            source_path=source_path,
            auxiliary_surface_points=None,
        )
        
    except MeshLoadError:
        # Re-raise our custom exceptions
        raise
    except Exception as e:
        # Catch any unexpected errors
        raise MeshLoadError(
            f"Unexpected error loading mesh: {e}",
            details={
                "path": str(path),
                "original_error": str(e),
                "error_type": "unexpected_error"
            }
        ) from e
