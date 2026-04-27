from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from mesh2cad.cad.build123d_builder import BuildResult
from mesh2cad.domain.reports import ValidationReport
from mesh2cad.mesh.io import MeshData
from mesh2cad.pipeline.align import icp_align_preview_to_source


@dataclass(slots=True)
class ValidationMetrics:
    source_volume: float | None
    built_volume: float | None
    source_extents: tuple[float, float, float]
    built_extents: tuple[float, float, float] | None


def validate_reconstruction(
    source_mesh: MeshData,
    build_result: BuildResult | None,
    *,
    sample_count: int = 2_500,
    align_surface_metrics: bool = True,
    icp_iterations: int = 10,
    icp_seed: int = 0,
) -> ValidationReport | None:
    """Compute validation metrics from source mesh and built CAD metadata."""
    if build_result is None:
        return None

    warnings = list(build_result.errors)
    if not build_result.success:
        return ValidationReport(solid_valid=False, warnings=warnings)

    metrics = _collect_metrics(source_mesh, build_result.metadata)
    volume_delta_ratio = _relative_delta(metrics.source_volume, metrics.built_volume)
    extents_delta = _extents_delta_ratio(metrics.source_extents, metrics.built_extents)

    preview_mesh = _load_preview_mesh(build_result.metadata.get("preview_stl_path"))
    surface_metrics = None
    raw_surface_metrics = None
    if preview_mesh is not None:
        raw_surface_metrics = _surface_distance_metrics_pair(
            source_mesh,
            preview_mesh,
            sample_count=sample_count,
        )
        if align_surface_metrics and raw_surface_metrics is not None:
            icp_samples = min(1200, max(200, sample_count))
            aux = source_mesh.auxiliary_surface_points
            icp_cloud = (
                np.asarray(aux, dtype=np.float64)
                if aux is not None and len(aux) >= 6
                else None
            )
            aligned = icp_align_preview_to_source(
                preview_mesh,
                source_mesh.mesh,
                samples=icp_samples,
                iterations=icp_iterations,
                seed=icp_seed,
                icp_target_points=icp_cloud,
            )
            surface_metrics = _surface_distance_metrics_pair(
                source_mesh,
                aligned,
                sample_count=sample_count,
            )
            if surface_metrics is not None and raw_surface_metrics is not None:
                if icp_cloud is not None:
                    warnings.append(
                        "ICP alignment used raw scan points (nearest-neighbor to auxiliary cloud)."
                    )
                warnings.append(
                    f"surface rms (ICP-aligned preview) {surface_metrics.rms_error:.6f}"
                )
                warnings.append(f"surface max (ICP-aligned) {surface_metrics.max_error:.6f}")
                warnings.append(f"surface rms (raw frame) {raw_surface_metrics.rms_error:.6f}")
        else:
            surface_metrics = raw_surface_metrics
            if surface_metrics is not None:
                warnings.append(f"surface rms error {surface_metrics.rms_error:.6f}")
                warnings.append(f"surface max error {surface_metrics.max_error:.6f}")

    if extents_delta is not None:
        warnings.append(f"bbox extents delta ratio {extents_delta:.6f}")
    if volume_delta_ratio is not None:
        warnings.append(f"volume delta ratio {volume_delta_ratio:.6f}")

    return ValidationReport(
        solid_valid=build_result.success,
        rms_error=surface_metrics.rms_error if surface_metrics is not None else extents_delta,
        max_error=surface_metrics.max_error if surface_metrics is not None else extents_delta,
        volume_delta_ratio=volume_delta_ratio,
        warnings=warnings,
    )


def _collect_metrics(source_mesh: MeshData, build_metadata: dict[str, Any]) -> ValidationMetrics:
    source_volume = None
    if source_mesh.mesh.is_volume:
        source_volume = float(abs(source_mesh.mesh.volume))

    source_extents = tuple(float(value) for value in source_mesh.mesh.extents.tolist())
    built_volume = _coerce_float(build_metadata.get("volume"))

    built_extents_value = build_metadata.get("bbox_extents")
    built_extents = None
    if isinstance(built_extents_value, (list, tuple)) and len(built_extents_value) == 3:
        built_extents = tuple(float(value) for value in built_extents_value)

    return ValidationMetrics(
        source_volume=source_volume,
        built_volume=built_volume,
        source_extents=source_extents,
        built_extents=built_extents,
    )


def _relative_delta(source_value: float | None, built_value: float | None) -> float | None:
    if source_value is None or built_value is None:
        return None
    if math.isclose(source_value, 0.0, abs_tol=1e-12):
        return None
    return abs(source_value - built_value) / abs(source_value)


def _extents_delta_ratio(
    source_extents: tuple[float, float, float],
    built_extents: tuple[float, float, float] | None,
) -> float | None:
    if built_extents is None:
        return None
    source = np.asarray(source_extents, dtype=np.float64)
    built = np.asarray(built_extents, dtype=np.float64)
    denom = np.where(np.abs(source) < 1e-12, 1.0, np.abs(source))
    return float(np.max(np.abs(source - built) / denom))


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class SurfaceDistanceMetrics:
    rms_error: float
    max_error: float


def _surface_distance_metrics_pair(
    source_mesh: MeshData,
    preview_mesh: trimesh.Trimesh,
    *,
    sample_count: int,
) -> SurfaceDistanceMetrics | None:
    try:
        aux = source_mesh.auxiliary_surface_points
        if aux is not None and len(aux) > 0:
            pts = np.asarray(aux, dtype=np.float64)
            if len(pts) > sample_count:
                rng = np.random.default_rng(0)
                idx = rng.choice(len(pts), size=sample_count, replace=False)
                source_points = pts[idx]
            else:
                source_points = pts
        else:
            source_points = source_mesh.mesh.sample(sample_count)
        built_points = preview_mesh.sample(sample_count)
        source_to_built = _point_to_mesh_distances(source_points, preview_mesh)
        built_to_source = _point_to_mesh_distances(built_points, source_mesh.mesh)
    except Exception:
        return None

    combined = np.concatenate((source_to_built, built_to_source))
    if combined.size == 0:
        return None

    return SurfaceDistanceMetrics(
        rms_error=float(np.sqrt(np.mean(np.square(combined)))),
        max_error=float(np.max(combined)),
    )


def _load_preview_mesh(preview_stl_path: Any) -> trimesh.Trimesh | None:
    if not isinstance(preview_stl_path, str) or not preview_stl_path:
        return None

    path = Path(preview_stl_path).expanduser()
    if not path.exists():
        return None

    loaded = trimesh.load_mesh(path, force="mesh")
    if not isinstance(loaded, trimesh.Trimesh):
        return None
    return loaded


def _point_to_mesh_distances(
    points: np.ndarray,
    target_mesh: trimesh.Trimesh,
) -> np.ndarray:
    try:
        query = trimesh.proximity.ProximityQuery(target_mesh)
        _, distances, _ = query.on_surface(points)
        return np.asarray(distances, dtype=np.float64)
    except ModuleNotFoundError:
        _, distances, _ = trimesh.proximity.closest_point_naive(target_mesh, points)
        return np.asarray(distances, dtype=np.float64)
