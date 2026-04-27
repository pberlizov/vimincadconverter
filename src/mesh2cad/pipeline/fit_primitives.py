from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import cKDTree

from mesh2cad.domain.primitives import (
    ConePrimitive,
    CylinderPrimitive,
    PlanePrimitive,
    Primitive,
    PrimitiveRegion,
    SpherePrimitive,
)
from mesh2cad.domain.types import Confidence, PrimitiveKind, ToleranceConfig
from mesh2cad.mesh.sampling import SampledCloud

Vec3 = NDArray[np.float64]


@dataclass(slots=True)
class PrimitiveFitResult:
    primitives: list[Primitive]
    leftover_point_indices: list[int]
    warnings: list[str]


def fit_primitives(
    cloud: SampledCloud,
    tolerances: ToleranceConfig,
) -> PrimitiveFitResult:
    """Fit an initial set of plane, cylinder, cone, and sphere primitives from a sampled cloud."""
    if cloud.normals is None or len(cloud.normals) == 0:
        return PrimitiveFitResult(
            primitives=[],
            leftover_point_indices=list(range(len(cloud.points))),
            warnings=["Point normals are required for primitive fitting."],
        )

    plane_primitives = _fit_planes(cloud, tolerances)
    plane_used_points = {
        point_index
        for primitive in plane_primitives
        for point_index in primitive.region.point_indices
    }
    leftover = sorted(set(range(len(cloud.points))) - plane_used_points)
    use_residual_cloud = len(leftover) >= max(100, int(len(cloud.points) * 0.08))
    if use_residual_cloud:
        cylinder_cloud, cylinder_index_map = _subset_cloud(cloud, leftover)
    else:
        cylinder_cloud = cloud
        cylinder_index_map = np.arange(len(cloud.points), dtype=np.int64)
    cylinder_primitives = _fit_cylinders(cylinder_cloud, tolerances=tolerances)
    _remap_cylinder_regions(cylinder_primitives, cylinder_index_map)
    cone_primitives = _fit_cones(cylinder_cloud, tolerances=tolerances)
    _remap_cone_regions(cone_primitives, cylinder_index_map)
    sphere_primitives = _fit_spheres(cylinder_cloud, tolerances=tolerances)
    _remap_sphere_regions(sphere_primitives, cylinder_index_map)

    primitives: list[Primitive] = [*plane_primitives]
    primitives.extend(cylinder_primitives)
    primitives.extend(cone_primitives)
    primitives.extend(sphere_primitives)

    used_points = {
        point_index
        for primitive in primitives
        for point_index in primitive.region.point_indices
    }
    leftover = sorted(set(range(len(cloud.points))) - used_points)

    warnings: list[str] = []
    if not plane_primitives:
        warnings.append("No plane primitives detected.")
    if not cylinder_primitives:
        warnings.append("No cylinder primitives detected.")
    if not cone_primitives:
        warnings.append("No cone primitives detected.")
    if not sphere_primitives:
        warnings.append("No sphere primitives detected.")

    return PrimitiveFitResult(
        primitives=primitives,
        leftover_point_indices=leftover,
        warnings=warnings,
    )


def _fit_planes(cloud: SampledCloud, tolerances: ToleranceConfig) -> list[PlanePrimitive]:
    normals = _normalize_vectors(cloud.normals)
    points = np.asarray(cloud.points, dtype=np.float64)

    orientation_buckets = _bucket_normals(normals)
    min_support = max(50, int(len(points) * 0.05))
    planes: list[PlanePrimitive] = []

    for bucket_indices in orientation_buckets.values():
        if len(bucket_indices) < min_support:
            continue

        representative_normal = _mean_direction(normals[bucket_indices])
        distances = points @ representative_normal
        bucket_distances = distances[bucket_indices]

        peak_centers = _distance_peaks(bucket_distances, tolerances.linear)
        for peak in peak_centers:
            close_mask = np.abs(distances - peak) <= max(tolerances.linear * 2.0, 1e-6)
            candidate_indices = np.flatnonzero(close_mask)
            if len(candidate_indices) < min_support:
                continue

            plane_points = points[candidate_indices]
            centroid = plane_points.mean(axis=0)
            residuals = np.abs((plane_points - centroid) @ representative_normal)
            if residuals.mean() > tolerances.linear:
                continue

            area_estimate = _projected_bbox_area(plane_points, representative_normal)
            if area_estimate < tolerances.min_region_area:
                continue

            confidence = Confidence(
                score=_plane_confidence(
                    support_count=len(candidate_indices),
                    total_count=len(points),
                    mean_residual=float(residuals.mean()),
                    tolerance=tolerances.linear,
                ),
                reasons=[
                    f"{len(candidate_indices)} supporting points",
                    f"mean residual {residuals.mean():.4f}",
                    f"projected area {area_estimate:.4f}",
                ],
            )

            planes.append(
                PlanePrimitive(
                    kind=PrimitiveKind.PLANE,
                    confidence=confidence,
                    region=PrimitiveRegion(
                        point_indices=candidate_indices.tolist(),
                        area=area_estimate,
                    ),
                    origin=centroid,
                    normal=representative_normal,
                )
            )

    return _deduplicate_planes(planes, tolerances)


def _normalize_vectors(vectors: NDArray[np.float64]) -> NDArray[np.float64]:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    safe_norms = np.where(norms == 0.0, 1.0, norms)
    return vectors / safe_norms


def _bucket_normals(normals: NDArray[np.float64]) -> dict[tuple[int, int, int], list[int]]:
    buckets: dict[tuple[int, int, int], list[int]] = {}
    for index, normal in enumerate(normals):
        canonical = normal.copy()
        first_nonzero = next((value for value in canonical if abs(value) > 1e-8), 0.0)
        if first_nonzero < 0:
            canonical *= -1.0

        key = tuple(np.round(canonical / 0.15).astype(int).tolist())
        buckets.setdefault(key, []).append(index)
    return buckets


def _mean_direction(vectors: NDArray[np.float64]) -> Vec3:
    mean = vectors.mean(axis=0)
    norm = np.linalg.norm(mean)
    if norm == 0.0:
        return np.array([0.0, 0.0, 1.0], dtype=np.float64)
    return mean / norm


def _distance_peaks(distances: NDArray[np.float64], linear_tolerance: float) -> list[float]:
    if len(distances) == 0:
        return []

    bucket_width = max(linear_tolerance * 2.0, 1e-3)
    buckets = np.round(distances / bucket_width).astype(int)
    unique, counts = np.unique(buckets, return_counts=True)
    min_count = max(10, int(len(distances) * 0.1))
    peaks = [
        bucket * bucket_width
        for bucket, count in zip(unique, counts, strict=False)
        if count >= min_count
    ]
    return sorted(peaks)


def _projected_bbox_area(points: NDArray[np.float64], normal: Vec3) -> float:
    tangent_a = _perpendicular_unit_vector(normal)
    tangent_b = np.cross(normal, tangent_a)
    projected = np.column_stack((points @ tangent_a, points @ tangent_b))
    extents = projected.max(axis=0) - projected.min(axis=0)
    return float(extents[0] * extents[1])


def _perpendicular_unit_vector(vector: Vec3) -> Vec3:
    reference = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    if abs(np.dot(reference, vector)) > 0.9:
        reference = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    perpendicular = np.cross(vector, reference)
    norm = np.linalg.norm(perpendicular)
    if norm == 0.0:
        return np.array([0.0, 0.0, 1.0], dtype=np.float64)
    return perpendicular / norm


def _plane_confidence(
    support_count: int,
    total_count: int,
    mean_residual: float,
    tolerance: float,
) -> float:
    support_ratio = support_count / max(total_count, 1)
    residual_penalty = min(mean_residual / max(tolerance, 1e-6), 1.0)
    return max(0.0, min(1.0, (support_ratio * 0.7) + ((1.0 - residual_penalty) * 0.3)))


def _deduplicate_planes(
    planes: list[PlanePrimitive],
    tolerances: ToleranceConfig,
) -> list[PlanePrimitive]:
    deduplicated: list[PlanePrimitive] = []
    for plane in sorted(planes, key=lambda item: item.confidence.score, reverse=True):
        duplicate = False
        for existing in deduplicated:
            aligned = abs(float(np.dot(plane.normal, existing.normal))) >= math.cos(
                math.radians(tolerances.angular_deg)
            )
            offset = abs(float(np.dot(plane.origin - existing.origin, existing.normal)))
            if aligned and offset <= tolerances.linear * 2.0:
                duplicate = True
                break

        if not duplicate:
            deduplicated.append(plane)
    return deduplicated


def _fit_cylinders(
    cloud: SampledCloud,
    tolerances: ToleranceConfig,
) -> list[CylinderPrimitive]:
    if cloud.normals is None or len(cloud.normals) == 0:
        return []

    points = np.asarray(cloud.points, dtype=np.float64)
    normals = np.asarray(cloud.normals, dtype=np.float64)
    if len(points) < max(100, int(len(cloud.points) * 0.08)):
        return []

    normalized_normals = _normalize_vectors(normals)
    normal_covariance = np.cov(normalized_normals, rowvar=False)
    eigenvalues, eigenvectors = np.linalg.eigh(normal_covariance)
    axis_direction = eigenvectors[:, np.argmin(eigenvalues)]
    axis_direction = axis_direction / max(np.linalg.norm(axis_direction), 1e-12)

    normal_axis_alignment = np.abs(normalized_normals @ axis_direction)
    sidewall_mask = normal_axis_alignment <= 0.25
    sidewall_indices = np.flatnonzero(sidewall_mask)
    if len(sidewall_indices) < max(100, int(len(cloud.points) * 0.08)):
        return []

    sidewall_points = points[sidewall_indices]
    sidewall_normals = normalized_normals[sidewall_indices]
    if float(np.mean(np.abs(sidewall_normals @ axis_direction))) > 0.15:
        return []

    basis_x = _perpendicular_unit_vector(axis_direction)
    basis_y = np.cross(axis_direction, basis_x)
    projected_points = np.column_stack((sidewall_points @ basis_x, sidewall_points @ basis_y))
    projected_normals = np.column_stack((sidewall_normals @ basis_x, sidewall_normals @ basis_y))
    cylinders: list[CylinderPrimitive] = []
    sidewall_clusters = _cluster_sidewall_components(projected_points, tolerances)

    for cluster_indices in sidewall_clusters:
        cluster_points = sidewall_points[cluster_indices]
        cluster_normals = sidewall_normals[cluster_indices]
        cluster_projected_points = projected_points[cluster_indices]
        cluster_projected_normals = projected_normals[cluster_indices]
        cluster_cloud_indices = sidewall_indices[cluster_indices]

        candidate_centers = _candidate_cylinder_centers(
            projected_points=cluster_projected_points,
            projected_normals=cluster_projected_normals,
            tolerances=tolerances,
        )

        for center_2d in candidate_centers:
            cylinder = _build_cylinder_from_center(
                center_2d=center_2d,
                axis_direction=axis_direction,
                basis_x=basis_x,
                basis_y=basis_y,
                cloud_points=points,
                sidewall_points=cluster_points,
                sidewall_normals=cluster_normals,
                sidewall_indices=cluster_cloud_indices,
                tolerances=tolerances,
            )
            if cylinder is not None:
                cylinders.append(cylinder)

    if not cylinders:
        candidate_centers = _candidate_cylinder_centers(
            projected_points=projected_points,
            projected_normals=projected_normals,
            tolerances=tolerances,
        )
        for center_2d in candidate_centers:
            cylinder = _build_cylinder_from_center(
                center_2d=center_2d,
                axis_direction=axis_direction,
                basis_x=basis_x,
                basis_y=basis_y,
                cloud_points=points,
                sidewall_points=sidewall_points,
                sidewall_normals=sidewall_normals,
                sidewall_indices=sidewall_indices,
                tolerances=tolerances,
            )
            if cylinder is not None:
                cylinders.append(cylinder)

    return _deduplicate_cylinders(cylinders, tolerances)


def _subset_cloud(
    cloud: SampledCloud,
    indices: list[int],
) -> tuple[SampledCloud, NDArray[np.int64]]:
    index_array = np.asarray(indices, dtype=np.int64)
    normals = None
    if cloud.normals is not None:
        normals = np.asarray(cloud.normals[index_array], dtype=np.float64)
    source_face_indices = None
    if cloud.source_face_indices is not None:
        source_face_indices = np.asarray(cloud.source_face_indices[index_array], dtype=np.int64)
    return (
        SampledCloud(
            points=np.asarray(cloud.points[index_array], dtype=np.float64),
            normals=normals,
            source_face_indices=source_face_indices,
        ),
        index_array,
    )


def _remap_cylinder_regions(
    cylinders: list[CylinderPrimitive],
    index_map: NDArray[np.int64],
) -> None:
    for cylinder in cylinders:
        cylinder.region.point_indices = index_map[
            np.asarray(cylinder.region.point_indices, dtype=np.int64)
        ].tolist()


def _remap_cone_regions(
    cones: list[ConePrimitive],
    index_map: NDArray[np.int64],
) -> None:
    for cone in cones:
        cone.region.point_indices = index_map[
            np.asarray(cone.region.point_indices, dtype=np.int64)
        ].tolist()


def _remap_sphere_regions(
    spheres: list[SpherePrimitive],
    index_map: NDArray[np.int64],
) -> None:
    for sphere in spheres:
        sphere.region.point_indices = index_map[
            np.asarray(sphere.region.point_indices, dtype=np.int64)
        ].tolist()


def _cylinder_confidence(
    support_count: int,
    total_count: int,
    mean_axis_alignment: float,
    radius_std: float,
    radius: float,
) -> float:
    support_ratio = support_count / max(total_count, 1)
    alignment_score = 1.0 - min(mean_axis_alignment / 0.2, 1.0)
    radius_score = 1.0 - min(radius_std / max(radius * 0.1, 1e-6), 1.0)
    return max(
        0.0,
        min(
            1.0,
            (support_ratio * 0.4) + (alignment_score * 0.3) + (radius_score * 0.3),
        ),
    )


def _candidate_cylinder_centers(
    *,
    projected_points: NDArray[np.float64],
    projected_normals: NDArray[np.float64],
    tolerances: ToleranceConfig,
) -> list[NDArray[np.float64]]:
    count = len(projected_points)
    if count < 2:
        return []

    step = max(1, count // 60)
    sample_indices = list(range(0, count, step))[:60]
    intersections: list[NDArray[np.float64]] = []

    for left_offset, left_index in enumerate(sample_indices):
        p1 = projected_points[left_index]
        n1 = projected_normals[left_index]
        if np.linalg.norm(n1) == 0.0:
            continue
        for right_index in sample_indices[left_offset + 1 :]:
            p2 = projected_points[right_index]
            n2 = projected_normals[right_index]
            determinant = float((n1[0] * -n2[1]) - (n1[1] * -n2[0]))
            if abs(determinant) < 1e-3:
                continue

            matrix = np.array([[n1[0], -n2[0]], [n1[1], -n2[1]]], dtype=np.float64)
            rhs = p2 - p1
            try:
                parameters = np.linalg.solve(matrix, rhs)
            except np.linalg.LinAlgError:
                continue
            intersection = p1 + (parameters[0] * n1)
            intersections.append(intersection)

    if not intersections:
        return []

    threshold = max(tolerances.linear * 4.0, 0.35)
    clusters = _cluster_points(np.asarray(intersections, dtype=np.float64), threshold)
    return [cluster.mean(axis=0) for cluster in clusters if len(cluster) >= 3]


def _cluster_sidewall_components(
    projected_points: NDArray[np.float64],
    tolerances: ToleranceConfig,
) -> list[NDArray[np.int64]]:
    if len(projected_points) == 0:
        return []

    neighbor_radius = max(tolerances.linear * 4.0, 0.35)
    tree = cKDTree(projected_points)
    visited = np.zeros(len(projected_points), dtype=bool)
    min_cluster_size = max(32, int(len(projected_points) * 0.03))
    clusters: list[NDArray[np.int64]] = []

    for start_index in range(len(projected_points)):
        if visited[start_index]:
            continue

        stack = [start_index]
        visited[start_index] = True
        component: list[int] = []

        while stack:
            current_index = stack.pop()
            component.append(current_index)
            neighbor_indices = tree.query_ball_point(projected_points[current_index], neighbor_radius)
            for neighbor_index in neighbor_indices:
                if not visited[neighbor_index]:
                    visited[neighbor_index] = True
                    stack.append(int(neighbor_index))

        if len(component) >= min_cluster_size:
            clusters.append(np.asarray(component, dtype=np.int64))

    return clusters


def _cluster_points(points: NDArray[np.float64], threshold: float) -> list[NDArray[np.float64]]:
    clusters: list[list[NDArray[np.float64]]] = []
    for point in points:
        matched_cluster: list[NDArray[np.float64]] | None = None
        for cluster in clusters:
            centroid = np.mean(np.asarray(cluster), axis=0)
            if float(np.linalg.norm(point - centroid)) <= threshold:
                matched_cluster = cluster
                break
        if matched_cluster is None:
            clusters.append([point])
        else:
            matched_cluster.append(point)
    return [np.asarray(cluster, dtype=np.float64) for cluster in clusters]


def _build_cylinder_from_center(
    *,
    center_2d: NDArray[np.float64],
    axis_direction: Vec3,
    basis_x: Vec3,
    basis_y: Vec3,
    cloud_points: NDArray[np.float64],
    sidewall_points: NDArray[np.float64],
    sidewall_normals: NDArray[np.float64],
    sidewall_indices: NDArray[np.int64],
    tolerances: ToleranceConfig,
) -> CylinderPrimitive | None:
    projected_points = np.column_stack((sidewall_points @ basis_x, sidewall_points @ basis_y))
    radial_vectors_2d = projected_points - center_2d
    radial_distances = np.linalg.norm(radial_vectors_2d, axis=1)
    if len(radial_distances) == 0:
        return None

    normalized_radials = np.divide(
        radial_vectors_2d,
        np.maximum(radial_distances[:, None], 1e-12),
    )
    projected_normals = np.column_stack((sidewall_normals @ basis_x, sidewall_normals @ basis_y))
    normal_alignment = np.abs(np.sum(normalized_radials * projected_normals, axis=1))

    radius_seed_mask = normal_alignment >= 0.98
    if int(np.sum(radius_seed_mask)) < 16:
        return None

    radius = float(np.median(radial_distances[radius_seed_mask]))
    radial_residual = np.abs(radial_distances - radius)
    support_mask = (radial_residual <= max(tolerances.linear * 3.0, radius * 0.08)) & (normal_alignment >= 0.9)
    support_indices = np.flatnonzero(support_mask)
    if len(support_indices) < max(40, int(len(sidewall_points) * 0.08)):
        return None

    support_angles = np.arctan2(
        projected_normals[support_indices, 1],
        projected_normals[support_indices, 0],
    )
    occupied_bins = np.unique(np.floor(((support_angles + math.pi) / (2.0 * math.pi)) * 12.0).astype(int))
    if len(occupied_bins) < 9:
        return None

    supported_sidewall_points = sidewall_points[support_indices]
    supported_cloud_indices = sidewall_indices[support_indices]
    axis_origin = (center_2d[0] * basis_x) + (center_2d[1] * basis_y)
    axis_origin = np.asarray(axis_origin, dtype=np.float64)

    axial_distances = (supported_sidewall_points - axis_origin) @ axis_direction
    all_axial_distances = (cloud_points - axis_origin) @ axis_direction
    height_estimate = float(all_axial_distances.max() - all_axial_distances.min())
    if height_estimate <= tolerances.linear * 2.0:
        return None

    radius_std = float(np.std(radial_distances[support_indices]))
    confidence = Confidence(
        score=_cylinder_confidence(
            support_count=len(supported_cloud_indices),
            total_count=len(cloud_points),
            mean_axis_alignment=float(np.mean(np.abs(sidewall_normals[support_indices] @ axis_direction))),
            radius_std=radius_std,
            radius=radius,
        ),
        reasons=[
            f"{len(supported_cloud_indices)} supporting points",
            f"radius {radius:.4f}",
            f"radius std {radius_std:.4f}",
            f"height {height_estimate:.4f}",
        ],
    )

    axis_origin_3d = axis_origin + (np.mean(axial_distances) * axis_direction)
    return CylinderPrimitive(
        kind=PrimitiveKind.CYLINDER,
        confidence=confidence,
        region=PrimitiveRegion(
            point_indices=supported_cloud_indices.tolist(),
            area=float(2.0 * math.pi * radius * height_estimate),
        ),
        axis_origin=np.asarray(axis_origin_3d, dtype=np.float64),
        axis_direction=np.asarray(axis_direction, dtype=np.float64),
        radius=radius,
        height_estimate=height_estimate,
    )


def _deduplicate_cylinders(
    cylinders: list[CylinderPrimitive],
    tolerances: ToleranceConfig,
) -> list[CylinderPrimitive]:
    deduplicated: list[CylinderPrimitive] = []
    for cylinder in sorted(cylinders, key=lambda item: item.confidence.score, reverse=True):
        duplicate = False
        for existing in deduplicated:
            axis_alignment = abs(float(np.dot(cylinder.axis_direction, existing.axis_direction)))
            center_distance = float(np.linalg.norm(cylinder.axis_origin - existing.axis_origin))
            radius_delta = abs(cylinder.radius - existing.radius)
            if (
                axis_alignment >= math.cos(math.radians(tolerances.angular_deg))
                and center_distance <= max(tolerances.linear * 4.0, cylinder.radius * 0.25)
                and radius_delta <= max(tolerances.linear * 2.0, cylinder.radius * 0.1)
            ):
                duplicate = True
                break
        if not duplicate:
            deduplicated.append(cylinder)
    return deduplicated


def _fit_cones(
    cloud: SampledCloud,
    tolerances: ToleranceConfig,
) -> list[ConePrimitive]:
    if cloud.normals is None or len(cloud.normals) == 0:
        return []

    points = np.asarray(cloud.points, dtype=np.float64)
    normals = np.asarray(cloud.normals, dtype=np.float64)
    if len(points) < max(100, int(len(cloud.points) * 0.08)):
        return []

    normalized_normals = _normalize_vectors(normals)
    normal_covariance = np.cov(normalized_normals, rowvar=False)
    eigenvalues, eigenvectors = np.linalg.eigh(normal_covariance)
    axis_direction = eigenvectors[:, np.argmin(eigenvalues)]
    axis_direction = axis_direction / max(np.linalg.norm(axis_direction), 1e-12)

    normal_axis_alignment = np.abs(normalized_normals @ axis_direction)
    sidewall_mask = normal_axis_alignment <= 0.55
    sidewall_indices = np.flatnonzero(sidewall_mask)
    if len(sidewall_indices) < max(100, int(len(cloud.points) * 0.08)):
        return []

    sidewall_points = points[sidewall_indices]
    sidewall_normals = normalized_normals[sidewall_indices]
    basis_x = _perpendicular_unit_vector(axis_direction)
    basis_y = np.cross(axis_direction, basis_x)
    projected_points = np.column_stack((sidewall_points @ basis_x, sidewall_points @ basis_y))
    projected_normals = np.column_stack((sidewall_normals @ basis_x, sidewall_normals @ basis_y))

    cones: list[ConePrimitive] = []
    sidewall_clusters = _cluster_sidewall_components(projected_points, tolerances)
    for cluster_indices in sidewall_clusters:
        cluster_points = sidewall_points[cluster_indices]
        cluster_normals = sidewall_normals[cluster_indices]
        cluster_projected_points = projected_points[cluster_indices]
        cluster_projected_normals = projected_normals[cluster_indices]
        cluster_cloud_indices = sidewall_indices[cluster_indices]

        candidate_centers = _candidate_cylinder_centers(
            projected_points=cluster_projected_points,
            projected_normals=cluster_projected_normals,
            tolerances=tolerances,
        )
        for center_2d in candidate_centers:
            cone = _build_cone_from_center(
                center_2d=center_2d,
                axis_direction=axis_direction,
                basis_x=basis_x,
                basis_y=basis_y,
                cloud_points=points,
                sidewall_points=cluster_points,
                sidewall_normals=cluster_normals,
                sidewall_indices=cluster_cloud_indices,
                tolerances=tolerances,
            )
            if cone is not None:
                cones.append(cone)

    return _deduplicate_cones(cones, tolerances)


def _build_cone_from_center(
    *,
    center_2d: NDArray[np.float64],
    axis_direction: Vec3,
    basis_x: Vec3,
    basis_y: Vec3,
    cloud_points: NDArray[np.float64],
    sidewall_points: NDArray[np.float64],
    sidewall_normals: NDArray[np.float64],
    sidewall_indices: NDArray[np.int64],
    tolerances: ToleranceConfig,
) -> ConePrimitive | None:
    projected_points = np.column_stack((sidewall_points @ basis_x, sidewall_points @ basis_y))
    radial_vectors_2d = projected_points - center_2d
    radial_distances = np.linalg.norm(radial_vectors_2d, axis=1)
    if len(radial_distances) < 40:
        return None

    axis_origin = (center_2d[0] * basis_x) + (center_2d[1] * basis_y)
    axis_origin = np.asarray(axis_origin, dtype=np.float64)
    axial_distances = (sidewall_points - axis_origin) @ axis_direction
    height_estimate = float(axial_distances.max() - axial_distances.min())
    if height_estimate <= tolerances.linear * 3.0:
        return None

    coeffs = np.polyfit(axial_distances, radial_distances, deg=1)
    slope = float(coeffs[0])
    intercept = float(coeffs[1])
    predicted_radii = (slope * axial_distances) + intercept
    residuals = np.abs(predicted_radii - radial_distances)
    if float(np.median(residuals)) > max(tolerances.linear * 2.0, np.median(radial_distances) * 0.08):
        return None

    min_radius = float(np.min(predicted_radii))
    max_radius = float(np.max(predicted_radii))
    if min_radius < -max(tolerances.linear * 2.0, 0.1):
        return None
    if max_radius <= tolerances.linear * 2.0:
        return None
    if (max_radius - max(min_radius, 0.0)) <= max(tolerances.linear * 2.5, max_radius * 0.18):
        return None
    if abs(slope) <= 0.04:
        return None

    normalized_radials = np.divide(
        radial_vectors_2d,
        np.maximum(radial_distances[:, None], 1e-12),
    )
    projected_normals = np.column_stack((sidewall_normals @ basis_x, sidewall_normals @ basis_y))
    normal_alignment = np.abs(np.sum(normalized_radials * projected_normals, axis=1))
    support_mask = (residuals <= max(tolerances.linear * 3.0, max_radius * 0.1)) & (normal_alignment >= 0.75)
    support_indices = np.flatnonzero(support_mask)
    if len(support_indices) < max(36, int(len(sidewall_points) * 0.08)):
        return None

    support_axial = axial_distances[support_indices]
    support_predicted = predicted_radii[support_indices]
    if float(np.max(support_predicted) - np.min(support_predicted)) <= max(tolerances.linear * 2.0, max_radius * 0.15):
        return None

    support_angles = np.arctan2(
        projected_normals[support_indices, 1],
        projected_normals[support_indices, 0],
    )
    occupied_bins = np.unique(np.floor(((support_angles + math.pi) / (2.0 * math.pi)) * 12.0).astype(int))
    if len(occupied_bins) < 8:
        return None

    apex_axial = -intercept / slope
    apex = axis_origin + (apex_axial * axis_direction)
    support_cloud_indices = sidewall_indices[support_indices]
    base_radius = float(np.max(support_predicted))
    top_radius = float(max(0.0, np.min(support_predicted)))
    semi_angle_deg = float(math.degrees(math.atan(abs(slope))))
    if semi_angle_deg < 2.5 or semi_angle_deg > 70.0:
        return None

    confidence = Confidence(
        score=_cone_confidence(
            support_count=len(support_cloud_indices),
            total_count=len(cloud_points),
            residual=float(np.mean(residuals[support_indices])),
            radius_span=base_radius - top_radius,
            base_radius=base_radius,
        ),
        reasons=[
            f"{len(support_cloud_indices)} supporting points",
            f"base radius {base_radius:.4f}",
            f"top radius {top_radius:.4f}",
            f"semi-angle {semi_angle_deg:.4f}",
        ],
    )

    return ConePrimitive(
        kind=PrimitiveKind.CONE,
        confidence=confidence,
        region=PrimitiveRegion(
            point_indices=support_cloud_indices.tolist(),
            area=float(math.pi * (base_radius + top_radius) * math.hypot(height_estimate, base_radius - top_radius)),
        ),
        apex=np.asarray(apex, dtype=np.float64),
        axis_direction=np.asarray(axis_direction, dtype=np.float64),
        base_radius=base_radius,
        top_radius=top_radius,
        semi_angle_deg=semi_angle_deg,
        height_estimate=height_estimate,
    )


def _cone_confidence(
    support_count: int,
    total_count: int,
    residual: float,
    radius_span: float,
    base_radius: float,
) -> float:
    support_ratio = support_count / max(total_count, 1)
    residual_score = 1.0 - min(residual / max(base_radius * 0.08, 1e-6), 1.0)
    taper_score = min(radius_span / max(base_radius, 1e-6), 1.0)
    return max(
        0.0,
        min(1.0, (support_ratio * 0.35) + (residual_score * 0.35) + (taper_score * 0.30)),
    )


def _deduplicate_cones(
    cones: list[ConePrimitive],
    tolerances: ToleranceConfig,
) -> list[ConePrimitive]:
    deduplicated: list[ConePrimitive] = []
    for cone in sorted(cones, key=lambda item: item.confidence.score, reverse=True):
        duplicate = False
        for existing in deduplicated:
            axis_alignment = abs(float(np.dot(cone.axis_direction, existing.axis_direction)))
            apex_distance = float(np.linalg.norm(cone.apex - existing.apex))
            base_delta = abs(cone.base_radius - existing.base_radius)
            top_delta = abs(cone.top_radius - existing.top_radius)
            if (
                axis_alignment >= math.cos(math.radians(tolerances.angular_deg * 1.5))
                and apex_distance <= max(tolerances.linear * 4.0, cone.base_radius * 0.35)
                and base_delta <= max(tolerances.linear * 2.0, cone.base_radius * 0.12)
                and top_delta <= max(tolerances.linear * 2.0, max(cone.top_radius, existing.top_radius, 1.0) * 0.12)
            ):
                duplicate = True
                break
        if not duplicate:
            deduplicated.append(cone)
    return deduplicated


def _fit_spheres(
    cloud: SampledCloud,
    tolerances: ToleranceConfig,
) -> list[SpherePrimitive]:
    if cloud.normals is None or len(cloud.normals) == 0:
        return []

    points = np.asarray(cloud.points, dtype=np.float64)
    normals = np.asarray(cloud.normals, dtype=np.float64)
    if len(points) < max(120, int(len(cloud.points) * 0.1)):
        return []

    normalized_normals = _normalize_vectors(normals)
    design = np.column_stack(
        (
            np.ones(len(points), dtype=np.float64),
            normalized_normals,
        )
    )

    solutions = [
        np.linalg.lstsq(design, points[:, axis_index], rcond=None)[0]
        for axis_index in range(3)
    ]
    center = np.array([float(solution[0]) for solution in solutions], dtype=np.float64)
    signed_radii = [float(solutions[axis_index][1 + axis_index]) for axis_index in range(3)]
    radius = float(np.median(np.abs(signed_radii)))
    if radius <= tolerances.linear * 2.0:
        return []

    reconstructed = center[None, :] + (radius * normalized_normals)
    alternate = center[None, :] - (radius * normalized_normals)
    residual_plus = np.linalg.norm(points - reconstructed, axis=1)
    residual_minus = np.linalg.norm(points - alternate, axis=1)
    if float(np.mean(residual_minus)) < float(np.mean(residual_plus)):
        residuals = residual_minus
    else:
        residuals = residual_plus

    support_mask = residuals <= max(tolerances.linear * 3.0, radius * 0.08)
    support_indices = np.flatnonzero(support_mask)
    if len(support_indices) < max(80, int(len(points) * 0.18)):
        return []

    support_points = points[support_indices]
    support_vectors = support_points - center[None, :]
    support_distances = np.linalg.norm(support_vectors, axis=1)
    radius_std = float(np.std(support_distances))
    if radius_std > max(tolerances.linear * 2.0, radius * 0.08):
        return []

    support_directions = _normalize_vectors(support_vectors)
    occupied_bins = np.unique(np.floor(((support_directions + 1.0) / 2.0) * 4.0).astype(int), axis=0)
    if len(occupied_bins) < 18:
        return []

    confidence = Confidence(
        score=_sphere_confidence(
            support_count=len(support_indices),
            total_count=len(points),
            residual=float(np.mean(residuals[support_indices])),
            radius_std=radius_std,
            radius=radius,
        ),
        reasons=[
            f"{len(support_indices)} supporting points",
            f"radius {radius:.4f}",
            f"radius std {radius_std:.4f}",
            f"mean residual {float(np.mean(residuals[support_indices])):.4f}",
        ],
    )

    return [
        SpherePrimitive(
            kind=PrimitiveKind.SPHERE,
            confidence=confidence,
            region=PrimitiveRegion(
                point_indices=support_indices.tolist(),
                area=float(4.0 * math.pi * radius * radius),
            ),
            center=center,
            radius=radius,
        )
    ]


def _sphere_confidence(
    support_count: int,
    total_count: int,
    residual: float,
    radius_std: float,
    radius: float,
) -> float:
    support_ratio = support_count / max(total_count, 1)
    residual_score = 1.0 - min(residual / max(radius * 0.08, 1e-6), 1.0)
    radius_score = 1.0 - min(radius_std / max(radius * 0.08, 1e-6), 1.0)
    return max(
        0.0,
        min(1.0, (support_ratio * 0.35) + (residual_score * 0.35) + (radius_score * 0.30)),
    )
