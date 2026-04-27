from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from scipy.spatial import ConvexHull, Delaunay, cKDTree

from mesh2cad.domain.features import BaseExtrudeFeature, Feature, ThroughHoleFeature
from mesh2cad.domain.primitives import CylinderPrimitive, PlanePrimitive, Primitive
from mesh2cad.domain.types import Confidence, FeatureKind, ToleranceConfig
from mesh2cad.mesh.analysis import SceneAnalysis
from mesh2cad.mesh.sampling import SampledCloud


@dataclass(slots=True)
class FeatureInferenceResult:
    features: list[Feature]
    warnings: list[str]


def infer_features(
    primitives: list[Primitive],
    scene: SceneAnalysis,
    cloud: SampledCloud,
    tolerances: ToleranceConfig,
) -> FeatureInferenceResult:
    """Infer a narrow first pass of CAD-like features from primitives."""
    del scene

    plane_primitives = [primitive for primitive in primitives if isinstance(primitive, PlanePrimitive)]
    cylinder_primitives = [
        primitive for primitive in primitives if isinstance(primitive, CylinderPrimitive)
    ]

    features: list[Feature] = []
    warnings: list[str] = []

    base_extrude = _infer_base_extrude(plane_primitives, cloud, tolerances)
    if base_extrude is None:
        warnings.append("No base extrusion inferred.")
        return FeatureInferenceResult(features=features, warnings=warnings)

    features.append(base_extrude)

    through_holes = _infer_through_holes(
        cylinder_primitives=cylinder_primitives,
        base_extrude=base_extrude,
        tolerances=tolerances,
    )
    if through_holes:
        features.extend(through_holes)
    else:
        warnings.append("No through holes inferred.")

    return FeatureInferenceResult(features=features, warnings=warnings)


def _infer_base_extrude(
    plane_primitives: list[PlanePrimitive],
    cloud: SampledCloud,
    tolerances: ToleranceConfig,
) -> BaseExtrudeFeature | None:
    best_pair: tuple[PlanePrimitive, PlanePrimitive] | None = None
    best_pair_score = -math.inf

    for left_index, left_plane in enumerate(plane_primitives):
        for right_plane in plane_primitives[left_index + 1 :]:
            alignment = abs(float(np.dot(left_plane.normal, right_plane.normal)))
            if alignment < math.cos(math.radians(tolerances.angular_deg)):
                continue

            separation = abs(
                float(np.dot(right_plane.origin - left_plane.origin, left_plane.normal))
            )
            if separation <= tolerances.linear * 2.0:
                continue

            pair_score = min(left_plane.region.area, right_plane.region.area)
            if pair_score > best_pair_score:
                best_pair = (left_plane, right_plane)
                best_pair_score = pair_score

    if best_pair is None:
        return None

    base_plane, opposite_plane = best_pair
    extrusion_axis = _canonical_axis(base_plane.normal, opposite_plane.origin - base_plane.origin)
    depth = abs(float(np.dot(opposite_plane.origin - base_plane.origin, extrusion_axis)))

    basis_x = _perpendicular_unit_vector(extrusion_axis)
    basis_y = np.cross(extrusion_axis, basis_x)

    support_indices = sorted(
        set(base_plane.region.point_indices).union(opposite_plane.region.point_indices)
    )
    support_points = np.asarray(cloud.points[support_indices], dtype=np.float64)
    local_x = (support_points - base_plane.origin) @ basis_x
    local_y = (support_points - base_plane.origin) @ basis_y

    profile_loop = _infer_profile_loop(local_x, local_y, tolerances)

    confidence = Confidence(
        score=min(1.0, (base_plane.confidence.score + opposite_plane.confidence.score) / 2.0),
        reasons=[
            "paired large parallel planes",
            f"extrusion depth {depth:.4f}",
            f"profile vertices {len(profile_loop)}",
        ],
    )

    return BaseExtrudeFeature(
        kind=FeatureKind.BASE_EXTRUDE,
        confidence=confidence,
        parameters={"depth": depth},
        references={},
        profile_loops=[profile_loop],
        depth=depth,
        sketch_plane={
            "origin": base_plane.origin,
            "x_dir": basis_x,
            "y_dir": basis_y,
            "z_dir": extrusion_axis,
        },
    )


def _infer_through_holes(
    cylinder_primitives: list[CylinderPrimitive],
    base_extrude: BaseExtrudeFeature,
    tolerances: ToleranceConfig,
) -> list[ThroughHoleFeature]:
    extrusion_axis = np.asarray(base_extrude.sketch_plane["z_dir"], dtype=np.float64)
    basis_x = np.asarray(base_extrude.sketch_plane["x_dir"], dtype=np.float64)
    basis_y = np.asarray(base_extrude.sketch_plane["y_dir"], dtype=np.float64)
    origin = np.asarray(base_extrude.sketch_plane["origin"], dtype=np.float64)
    profile_loop = base_extrude.profile_loops[0]

    holes: list[ThroughHoleFeature] = []
    for cylinder in cylinder_primitives:
        alignment = abs(float(np.dot(cylinder.axis_direction, extrusion_axis)))
        if alignment < math.cos(math.radians(tolerances.angular_deg * 2.0)):
            continue

        if cylinder.height_estimate is None:
            continue

        if cylinder.height_estimate < base_extrude.depth * 0.75:
            continue

        offset = np.asarray(cylinder.axis_origin, dtype=np.float64) - origin
        center_x = float(np.dot(offset, basis_x))
        center_y = float(np.dot(offset, basis_y))
        center_xy = (center_x, center_y)

        confidence = Confidence(
            score=min(1.0, (cylinder.confidence.score * 0.8) + 0.2),
            reasons=[
                "cylinder axis aligned to extrusion axis",
                f"hole radius {cylinder.radius:.4f}",
                f"support height {cylinder.height_estimate:.4f}",
            ],
        )

        holes.append(
            ThroughHoleFeature(
                kind=FeatureKind.THROUGH_HOLE,
                confidence=confidence,
                parameters={
                    "center_xy": center_xy,
                    "radius": cylinder.radius,
                    "depth": base_extrude.depth,
                },
                references={},
                center_xy=center_xy,
                radius=cylinder.radius,
                depth=base_extrude.depth,
            )
        )

    deduplicated = _deduplicate_holes(holes, tolerances)
    return _select_plausible_hole_family(
        holes=deduplicated,
        profile_loop=profile_loop,
        base_extrude=base_extrude,
        tolerances=tolerances,
    )


def _canonical_axis(normal: np.ndarray, separation_vector: np.ndarray) -> np.ndarray:
    axis = np.asarray(normal, dtype=np.float64)
    axis = axis / max(np.linalg.norm(axis), 1e-12)
    if float(np.dot(axis, separation_vector)) < 0.0:
        axis *= -1.0
    return axis


def _perpendicular_unit_vector(vector: np.ndarray) -> np.ndarray:
    reference = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    if abs(float(np.dot(reference, vector))) > 0.9:
        reference = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    perpendicular = np.cross(vector, reference)
    norm = np.linalg.norm(perpendicular)
    if norm == 0.0:
        return np.array([0.0, 0.0, 1.0], dtype=np.float64)
    return perpendicular / norm


def _infer_profile_loop(
    local_x: np.ndarray,
    local_y: np.ndarray,
    tolerances: ToleranceConfig,
) -> list[tuple[float, float]]:
    points_2d = np.column_stack((local_x, local_y))
    if len(points_2d) < 3:
        raise ValueError("At least three points are required to infer a profile loop.")

    concave_loop = _concave_profile_loop(points_2d, tolerances)
    if concave_loop is not None:
        return concave_loop

    return _convex_profile_loop(points_2d)


def _convex_profile_loop(points_2d: np.ndarray) -> list[tuple[float, float]]:
    if len(points_2d) < 3:
        raise ValueError("At least three points are required to infer a profile loop.")

    hull = ConvexHull(points_2d)
    hull_points = points_2d[hull.vertices]
    return [(float(point[0]), float(point[1])) for point in hull_points]


def _concave_profile_loop(
    points_2d: np.ndarray,
    tolerances: ToleranceConfig,
) -> list[tuple[float, float]] | None:
    snapped_points = _deduplicate_points(points_2d, tolerances)
    if len(snapped_points) < 8:
        return None

    try:
        triangulation = Delaunay(snapped_points)
    except Exception:
        return None

    radius_threshold = _triangle_radius_threshold(snapped_points, tolerances)
    boundary_edges: dict[tuple[int, int], int] = {}

    for simplex in triangulation.simplices:
        triangle = snapped_points[np.asarray(simplex, dtype=np.int64)]
        circumradius = _triangle_circumradius(triangle)
        if not np.isfinite(circumradius) or circumradius > radius_threshold:
            continue

        for start_index, end_index in ((0, 1), (1, 2), (2, 0)):
            edge = tuple(sorted((int(simplex[start_index]), int(simplex[end_index]))))
            boundary_edges[edge] = boundary_edges.get(edge, 0) + 1

    exterior_edges = [edge for edge, count in boundary_edges.items() if count == 1]
    if len(exterior_edges) < 3:
        return None

    loop = _largest_boundary_loop(exterior_edges, snapped_points)
    if loop is None or len(loop) < 4:
        return None

    simplified_loop = _simplify_collinear_vertices(loop, tolerances)
    if len(simplified_loop) < 3:
        return None

    if abs(_signed_polygon_area(simplified_loop)) < tolerances.min_region_area:
        return None

    if _signed_polygon_area(simplified_loop) < 0.0:
        simplified_loop.reverse()

    convex_area = abs(_signed_polygon_area(_convex_profile_loop(snapped_points)))
    concave_area = abs(_signed_polygon_area(simplified_loop))
    if concave_area >= convex_area * 0.995:
        return None

    return simplified_loop


def _deduplicate_points(points_2d: np.ndarray, tolerances: ToleranceConfig) -> np.ndarray:
    quantization = max(tolerances.linear * 0.5, 1e-6)
    buckets: dict[tuple[int, int], np.ndarray] = {}
    for point in points_2d:
        key = (
            int(round(float(point[0]) / quantization)),
            int(round(float(point[1]) / quantization)),
        )
        buckets.setdefault(key, point)
    return np.asarray(list(buckets.values()), dtype=np.float64)


def _triangle_radius_threshold(points_2d: np.ndarray, tolerances: ToleranceConfig) -> float:
    if len(points_2d) < 4:
        return math.inf

    tree = cKDTree(points_2d)
    distances, _ = tree.query(points_2d, k=2)
    nearest_neighbor = distances[:, 1]
    spacing = float(np.median(nearest_neighbor))
    spacing = max(spacing, tolerances.linear, 1e-6)
    return spacing * 2.5


def _triangle_circumradius(triangle: np.ndarray) -> float:
    side_a = float(np.linalg.norm(triangle[1] - triangle[0]))
    side_b = float(np.linalg.norm(triangle[2] - triangle[1]))
    side_c = float(np.linalg.norm(triangle[0] - triangle[2]))
    semiperimeter = (side_a + side_b + side_c) / 2.0
    area_term = (
        semiperimeter
        * (semiperimeter - side_a)
        * (semiperimeter - side_b)
        * (semiperimeter - side_c)
    )
    if area_term <= 1e-12:
        return math.inf
    area = math.sqrt(area_term)
    return (side_a * side_b * side_c) / max(4.0 * area, 1e-12)


def _largest_boundary_loop(
    boundary_edges: list[tuple[int, int]],
    points_2d: np.ndarray,
) -> list[tuple[float, float]] | None:
    adjacency: dict[int, set[int]] = {}
    remaining_edges = {tuple(sorted(edge)) for edge in boundary_edges}
    for left_index, right_index in remaining_edges:
        adjacency.setdefault(left_index, set()).add(right_index)
        adjacency.setdefault(right_index, set()).add(left_index)

    loops: list[list[tuple[float, float]]] = []
    while remaining_edges:
        start_edge = next(iter(remaining_edges))
        start_vertex = start_edge[0]
        current_vertex = start_vertex
        previous_vertex = None
        ordered_vertices = [start_vertex]

        while True:
            neighbors = adjacency.get(current_vertex, set())
            candidate_neighbors = [index for index in neighbors if index != previous_vertex]
            if not candidate_neighbors:
                break

            if previous_vertex is None:
                next_vertex = min(
                    candidate_neighbors,
                    key=lambda index: (
                        float(points_2d[index][0]),
                        float(points_2d[index][1]),
                    ),
                )
            else:
                next_vertex = candidate_neighbors[0]

            edge = tuple(sorted((current_vertex, next_vertex)))
            if edge not in remaining_edges:
                break

            remaining_edges.remove(edge)
            previous_vertex, current_vertex = current_vertex, next_vertex
            if current_vertex == start_vertex:
                break
            ordered_vertices.append(current_vertex)

        if len(ordered_vertices) >= 3 and current_vertex == start_vertex:
            loops.append(
                [
                    (float(points_2d[index][0]), float(points_2d[index][1]))
                    for index in ordered_vertices
                ]
            )
        else:
            continue

    if not loops:
        return None

    return max(loops, key=lambda loop: abs(_signed_polygon_area(loop)))


def _simplify_collinear_vertices(
    loop: list[tuple[float, float]],
    tolerances: ToleranceConfig,
) -> list[tuple[float, float]]:
    if len(loop) < 4:
        return loop

    simplified: list[tuple[float, float]] = []
    threshold = max(tolerances.linear * 0.25, 1e-6)
    for index, current_point in enumerate(loop):
        previous_point = np.asarray(loop[index - 1], dtype=np.float64)
        point = np.asarray(current_point, dtype=np.float64)
        next_point = np.asarray(loop[(index + 1) % len(loop)], dtype=np.float64)
        previous_edge = point - previous_point
        next_edge = next_point - point
        cross_value = abs(
            (previous_edge[0] * next_edge[1]) - (previous_edge[1] * next_edge[0])
        )
        if cross_value <= threshold:
            continue
        simplified.append(current_point)

    return simplified if len(simplified) >= 3 else loop


def _signed_polygon_area(loop: list[tuple[float, float]]) -> float:
    area = 0.0
    for index, point in enumerate(loop):
        next_point = loop[(index + 1) % len(loop)]
        area += (point[0] * next_point[1]) - (next_point[0] * point[1])
    return area / 2.0


def _hole_fits_profile(
    *,
    center_xy: tuple[float, float],
    radius: float,
    profile_loop: list[tuple[float, float]],
    tolerances: ToleranceConfig,
) -> bool:
    if not _point_in_polygon(center_xy, profile_loop):
        return False

    clearance = _point_to_polygon_edges_distance(center_xy, profile_loop)
    minimum_clearance = max(radius - (tolerances.linear * 1.5), radius * 0.75)
    return clearance >= minimum_clearance


def _select_plausible_hole_family(
    *,
    holes: list[ThroughHoleFeature],
    profile_loop: list[tuple[float, float]],
    base_extrude: BaseExtrudeFeature,
    tolerances: ToleranceConfig,
) -> list[ThroughHoleFeature]:
    if len(holes) <= 2:
        return holes

    plausible_holes = [
        hole
        for hole in holes
        if _point_in_polygon(hole.center_xy, profile_loop)
        and _point_to_polygon_edges_distance(hole.center_xy, profile_loop)
        >= max(hole.radius * 0.9, tolerances.linear * 2.0)
    ]
    candidates = plausible_holes if len(plausible_holes) >= 2 else holes

    families = _group_holes_by_radius(candidates, tolerances)
    strong_families = [family for family in families if len(family) >= 2]
    if not strong_families:
        return holes

    selected_family = min(
        strong_families,
        key=lambda family: (
            -len(family),
            np.median([hole.radius for hole in family]),
            -np.mean([hole.confidence.score for hole in family]),
        ),
    )

    if np.median([hole.radius for hole in selected_family]) > max(base_extrude.depth * 0.75, tolerances.linear * 4.0):
        return holes

    return sorted(selected_family, key=lambda hole: (hole.center_xy[0], hole.center_xy[1]))


def _group_holes_by_radius(
    holes: list[ThroughHoleFeature],
    tolerances: ToleranceConfig,
) -> list[list[ThroughHoleFeature]]:
    families: list[list[ThroughHoleFeature]] = []
    for hole in sorted(holes, key=lambda item: item.radius):
        matched_family: list[ThroughHoleFeature] | None = None
        for family in families:
            median_radius = float(np.median([member.radius for member in family]))
            threshold = max(tolerances.linear * 1.5, median_radius * 0.15)
            if abs(hole.radius - median_radius) <= threshold:
                matched_family = family
                break
        if matched_family is None:
            families.append([hole])
        else:
            matched_family.append(hole)
    return families


def _point_in_polygon(
    point: tuple[float, float],
    polygon: list[tuple[float, float]],
) -> bool:
    x_coord, y_coord = point
    inside = False
    for index, start_point in enumerate(polygon):
        end_point = polygon[(index + 1) % len(polygon)]
        x1, y1 = start_point
        x2, y2 = end_point
        intersects = ((y1 > y_coord) != (y2 > y_coord)) and (
            x_coord < ((x2 - x1) * (y_coord - y1) / max(y2 - y1, 1e-12)) + x1
        )
        if intersects:
            inside = not inside
    return inside


def _point_to_polygon_edges_distance(
    point: tuple[float, float],
    polygon: list[tuple[float, float]],
) -> float:
    point_array = np.asarray(point, dtype=np.float64)
    distances = [
        _point_to_segment_distance(
            point_array,
            np.asarray(polygon[index], dtype=np.float64),
            np.asarray(polygon[(index + 1) % len(polygon)], dtype=np.float64),
        )
        for index in range(len(polygon))
    ]
    return float(min(distances)) if distances else 0.0


def _point_to_segment_distance(
    point: np.ndarray,
    segment_start: np.ndarray,
    segment_end: np.ndarray,
) -> float:
    segment = segment_end - segment_start
    length_squared = float(np.dot(segment, segment))
    if length_squared <= 1e-12:
        return float(np.linalg.norm(point - segment_start))

    parameter = float(np.dot(point - segment_start, segment) / length_squared)
    parameter = min(1.0, max(0.0, parameter))
    projection = segment_start + (parameter * segment)
    return float(np.linalg.norm(point - projection))


def _deduplicate_holes(
    holes: list[ThroughHoleFeature],
    tolerances: ToleranceConfig,
) -> list[ThroughHoleFeature]:
    deduplicated: list[ThroughHoleFeature] = []
    for hole in sorted(holes, key=lambda item: (item.center_xy[0], item.center_xy[1], item.radius)):
        duplicate = False
        for existing in deduplicated:
            center_delta = math.dist(hole.center_xy, existing.center_xy)
            radius_delta = abs(hole.radius - existing.radius)
            if (
                center_delta <= max(tolerances.linear * 2.0, hole.radius * 0.2)
                and radius_delta <= max(tolerances.linear * 2.0, hole.radius * 0.1)
            ):
                duplicate = True
                break
        if not duplicate:
            deduplicated.append(hole)
    return deduplicated
