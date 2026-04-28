from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from scipy.spatial import ConvexHull, Delaunay, cKDTree

from mesh2cad.domain.features import (
    BaseExtrudeFeature,
    BlindHoleFeature,
    BossFeature,
    CounterSinkHoleFeature,
    Feature,
    PocketFeature,
    SphericalBossFeature,
    SphericalCavityFeature,
    ThroughHoleFeature,
)

# Cylinder height (along stock) vs stock depth: stricter split reduces mis-labeling.
_THROUGH_CYLINDER_MIN_DEPTH_RATIO = 0.78
_BLIND_CYLINDER_MAX_DEPTH_RATIO = 0.58
_BLIND_CYLINDER_MIN_DEPTH_RATIO = 0.20
from mesh2cad.domain.primitives import ConePrimitive, CylinderPrimitive, PlanePrimitive, Primitive, SpherePrimitive
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
    """Infer a narrow first pass of CAD-like features from primitives.

    Currently supported feature inference includes:
    - base extrusion from paired parallel planes
    - through-holes from cylinder primitives, including angled hole axes where the cylinder axis crosses the base stock faces
    - complemented rotational inference for strong cylinder-driven revolve solids
    """
    del scene

    plane_primitives = [primitive for primitive in primitives if isinstance(primitive, PlanePrimitive)]
    cylinder_primitives = [
        primitive for primitive in primitives if isinstance(primitive, CylinderPrimitive)
    ]
    cone_primitives = [primitive for primitive in primitives if isinstance(primitive, ConePrimitive)]
    sphere_primitives = [primitive for primitive in primitives if isinstance(primitive, SpherePrimitive)]

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
    countersink_holes = _infer_countersink_holes(
        cone_primitives=cone_primitives,
        through_holes=through_holes,
        base_extrude=base_extrude,
        cloud=cloud,
        tolerances=tolerances,
    )
    matched_countersinks = {
        (feature.center_xy, feature.hole_radius)
        for feature in countersink_holes
    }
    remaining_through_holes = [
        hole
        for hole in through_holes
        if not any(
            math.dist(hole.center_xy, center_xy)
            <= max(tolerances.linear * 3.0, hole.radius * 0.25, hole_radius * 0.25)
            and abs(hole.radius - hole_radius)
            <= max(tolerances.linear * 2.0, hole.radius * 0.12, hole_radius * 0.12)
            for center_xy, hole_radius in matched_countersinks
        )
    ]

    if remaining_through_holes:
        features.extend(remaining_through_holes)
    elif cylinder_primitives and not countersink_holes:
        warnings.append("No through holes inferred from available cylinders.")

    if countersink_holes:
        features.extend(countersink_holes)

    blind_holes = _infer_blind_holes(
        cylinder_primitives=cylinder_primitives,
        base_extrude=base_extrude,
        through_holes=remaining_through_holes,
        tolerances=tolerances,
    )
    if blind_holes:
        features.extend(blind_holes)

    reserved_centers = [(h.center_xy, h.radius) for h in remaining_through_holes] + [
        (h.center_xy, h.radius) for h in blind_holes
    ]
    bosses = _infer_bosses(
        cylinder_primitives=cylinder_primitives,
        base_extrude=base_extrude,
        tolerances=tolerances,
        reserved_hole_centers=reserved_centers,
    )
    if bosses:
        features.extend(bosses)

    spherical_bosses, spherical_cavities = _infer_spherical_modifiers(
        sphere_primitives=sphere_primitives,
        base_extrude=base_extrude,
        tolerances=tolerances,
    )
    if spherical_bosses:
        features.extend(spherical_bosses)
    if spherical_cavities:
        features.extend(spherical_cavities)

    pockets = _infer_planar_pockets(
        plane_primitives=plane_primitives,
        base_extrude=base_extrude,
        cloud=cloud,
        tolerances=tolerances,
    )
    if pockets:
        features.extend(pockets)

    return FeatureInferenceResult(features=features, warnings=warnings)


def _infer_spherical_modifiers(
    *,
    sphere_primitives: list[SpherePrimitive],
    base_extrude: BaseExtrudeFeature,
    tolerances: ToleranceConfig,
) -> tuple[list[SphericalBossFeature], list[SphericalCavityFeature]]:
    if not sphere_primitives:
        return [], []

    basis_x = np.asarray(base_extrude.sketch_plane["x_dir"], dtype=np.float64)
    basis_y = np.asarray(base_extrude.sketch_plane["y_dir"], dtype=np.float64)
    extrusion_axis = np.asarray(base_extrude.sketch_plane["z_dir"], dtype=np.float64)
    origin = np.asarray(base_extrude.sketch_plane["origin"], dtype=np.float64)
    depth = float(base_extrude.depth)
    profile_loop = base_extrude.profile_loops[0]
    face_tol = max(tolerances.linear * 3.0, depth * 0.08)

    bosses: list[SphericalBossFeature] = []
    cavities: list[SphericalCavityFeature] = []
    for sphere in sphere_primitives:
        center = np.asarray(sphere.center, dtype=np.float64)
        offset = center - origin
        center_xy = (float(np.dot(offset, basis_x)), float(np.dot(offset, basis_y)))
        center_offset = float(np.dot(offset, extrusion_axis))
        radius = float(sphere.radius)
        if radius <= tolerances.linear * 2.0:
            continue

        if not _point_in_polygon(center_xy, profile_loop):
            continue
        if _point_to_polygon_edges_distance(center_xy, profile_loop) < max(
            tolerances.linear * 2.0,
            radius * 0.35,
        ):
            continue

        confidence = Confidence(
            score=min(1.0, (sphere.confidence.score * 0.78) + 0.14),
            reasons=[
                f"sphere radius {radius:.4f}",
                f"center offset {center_offset:.4f}",
                "sphere intersects a stock face",
            ],
        )

        if center_offset < 0.0 and abs(center_offset) < radius + face_tol:
            bosses.append(
                SphericalBossFeature(
                    kind=FeatureKind.SPHERICAL_BOSS,
                    confidence=confidence,
                    parameters={"center_xy": center_xy, "center_offset": center_offset, "radius": radius},
                    references={},
                    center_xy=center_xy,
                    center_offset=center_offset,
                    radius=radius,
                )
            )
            continue
        if center_offset > depth and abs(center_offset - depth) < radius + face_tol:
            bosses.append(
                SphericalBossFeature(
                    kind=FeatureKind.SPHERICAL_BOSS,
                    confidence=confidence,
                    parameters={"center_xy": center_xy, "center_offset": center_offset, "radius": radius},
                    references={},
                    center_xy=center_xy,
                    center_offset=center_offset,
                    radius=radius,
                )
            )
            continue
        if 0.0 < center_offset < radius + face_tol:
            cavities.append(
                SphericalCavityFeature(
                    kind=FeatureKind.SPHERICAL_CAVITY,
                    confidence=confidence,
                    parameters={"center_xy": center_xy, "center_offset": center_offset, "radius": radius},
                    references={},
                    center_xy=center_xy,
                    center_offset=center_offset,
                    radius=radius,
                )
            )
            continue
        if depth - radius - face_tol < center_offset < depth:
            cavities.append(
                SphericalCavityFeature(
                    kind=FeatureKind.SPHERICAL_CAVITY,
                    confidence=confidence,
                    parameters={"center_xy": center_xy, "center_offset": center_offset, "radius": radius},
                    references={},
                    center_xy=center_xy,
                    center_offset=center_offset,
                    radius=radius,
                )
            )

    return _deduplicate_spherical_bosses(bosses, tolerances), _deduplicate_spherical_cavities(cavities, tolerances)


def _infer_countersink_holes(
    *,
    cone_primitives: list[ConePrimitive],
    through_holes: list[ThroughHoleFeature],
    base_extrude: BaseExtrudeFeature,
    cloud: SampledCloud,
    tolerances: ToleranceConfig,
) -> list[CounterSinkHoleFeature]:
    if not cone_primitives or not through_holes:
        return []

    extrusion_axis = np.asarray(base_extrude.sketch_plane["z_dir"], dtype=np.float64)
    basis_x = np.asarray(base_extrude.sketch_plane["x_dir"], dtype=np.float64)
    basis_y = np.asarray(base_extrude.sketch_plane["y_dir"], dtype=np.float64)
    origin = np.asarray(base_extrude.sketch_plane["origin"], dtype=np.float64)
    depth = float(base_extrude.depth)

    countersinks: list[CounterSinkHoleFeature] = []
    for cone in cone_primitives:
        alignment = abs(float(np.dot(cone.axis_direction, extrusion_axis)))
        if alignment < math.cos(math.radians(tolerances.angular_deg * 2.5)):
            continue
        if cone.height_estimate is None or cone.height_estimate <= tolerances.linear * 2.0:
            continue

        support_points = np.asarray(cloud.points[cone.region.point_indices], dtype=np.float64)
        if len(support_points) < 8:
            continue
        local_x = (support_points - origin) @ basis_x
        local_y = (support_points - origin) @ basis_y
        local_z = (support_points - origin) @ extrusion_axis
        center_xy = (float(np.mean(local_x)), float(np.mean(local_y)))
        z_min = float(np.min(local_z))
        z_max = float(np.max(local_z))
        face_tol = max(tolerances.linear * 3.0, depth * 0.08)
        if abs(z_min) <= face_tol and z_max < depth - face_tol:
            start_from_top = False
        elif abs(z_max - depth) <= face_tol and z_min > face_tol:
            start_from_top = True
        else:
            continue

        match: ThroughHoleFeature | None = None
        for hole in through_holes:
            center_delta = math.dist(center_xy, hole.center_xy)
            if center_delta <= max(tolerances.linear * 3.0, hole.radius * 0.3):
                match = hole
                break
        if match is None:
            continue

        alignment = abs(float(np.dot(cone.axis_direction, np.asarray(match.axis_direction, dtype=np.float64))))
        if alignment < math.cos(math.radians(tolerances.angular_deg * 2.5)):
            continue

        counter_sink_radius = float(max(cone.base_radius, cone.top_radius))
        if counter_sink_radius <= match.radius + max(tolerances.linear * 1.5, match.radius * 0.08):
            continue

        confidence = Confidence(
            score=min(1.0, (cone.confidence.score * 0.78) + 0.15),
            reasons=[
                "aligned cone matched to through-hole axis",
                f"hole radius {match.radius:.4f}",
                f"countersink radius {counter_sink_radius:.4f}",
                f"cone angle {cone.semi_angle_deg * 2.0:.4f}",
            ],
        )
        countersinks.append(
            CounterSinkHoleFeature(
                kind=FeatureKind.COUNTERSINK_HOLE,
                confidence=confidence,
                parameters={
                    "center_xy": center_xy,
                    "hole_radius": match.radius,
                    "counter_sink_radius": counter_sink_radius,
                    "counter_sink_angle_deg": cone.semi_angle_deg * 2.0,
                    "start_from_top": start_from_top,
                    "axis_origin": match.axis_origin,
                    "axis_direction": match.axis_direction,
                },
                references={},
                center_xy=center_xy,
                hole_radius=float(match.radius),
                counter_sink_radius=counter_sink_radius,
                counter_sink_angle_deg=float(cone.semi_angle_deg * 2.0),
                start_from_top=start_from_top,
                axis_origin=match.axis_origin,
                axis_direction=match.axis_direction,
            )
        )

    return _deduplicate_countersinks(countersinks, tolerances)


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
    """Infer through-hole features from cylinder primitives.

    This path supports holes whose axis is not exactly aligned with the extrusion axis,
    provided the cylinder passes through the inferred stock faces and the entry/exit
    points lie within or near the base profile.
    """
    extrusion_axis = np.asarray(base_extrude.sketch_plane["z_dir"], dtype=np.float64)
    basis_x = np.asarray(base_extrude.sketch_plane["x_dir"], dtype=np.float64)
    basis_y = np.asarray(base_extrude.sketch_plane["y_dir"], dtype=np.float64)
    origin = np.asarray(base_extrude.sketch_plane["origin"], dtype=np.float64)
    profile_loop = base_extrude.profile_loops[0]

    holes: list[ThroughHoleFeature] = []
    for cylinder in cylinder_primitives:
        if cylinder.height_estimate is None:
            continue

        axis_origin = np.asarray(cylinder.axis_origin, dtype=np.float64)
        axis_direction = np.asarray(cylinder.axis_direction, dtype=np.float64)
        axis_direction = axis_direction / max(np.linalg.norm(axis_direction), 1e-12)
        axis_z_origin = float(np.dot(axis_origin - origin, extrusion_axis))
        denom = float(np.dot(axis_direction, extrusion_axis))
        if abs(denom) < 0.1:
            continue

        t0 = -axis_z_origin / denom
        t1 = (float(base_extrude.depth) - axis_z_origin) / denom
        entry_t, exit_t = sorted((t0, t1))
        hole_length = float(abs(exit_t - entry_t))
        if hole_length < max(base_extrude.depth * 0.45, tolerances.linear * 4.0):
            continue
        if cylinder.height_estimate is None or cylinder.height_estimate < hole_length * _THROUGH_CYLINDER_MIN_DEPTH_RATIO:
            continue

        entry_pt = axis_origin + axis_direction * entry_t
        exit_pt = axis_origin + axis_direction * exit_t

        entry_z = float(np.dot(entry_pt - origin, extrusion_axis))
        exit_z = float(np.dot(exit_pt - origin, extrusion_axis))
        if not (
            abs(entry_z) <= tolerances.linear * 2.0
            or abs(entry_z - base_extrude.depth) <= tolerances.linear * 2.0
        ):
            continue
        if not (
            abs(exit_z) <= tolerances.linear * 2.0
            or abs(exit_z - base_extrude.depth) <= tolerances.linear * 2.0
        ):
            continue

        entry_xy = (
            float(np.dot(entry_pt - origin, basis_x)),
            float(np.dot(entry_pt - origin, basis_y)),
        )
        exit_xy = (
            float(np.dot(exit_pt - origin, basis_x)),
            float(np.dot(exit_pt - origin, basis_y)),
        )
        if not _hole_fits_profile(
            center_xy=entry_xy,
            radius=cylinder.radius,
            profile_loop=profile_loop,
            tolerances=tolerances,
        ) and not _hole_fits_profile(
            center_xy=exit_xy,
            radius=cylinder.radius,
            profile_loop=profile_loop,
            tolerances=tolerances,
        ):
            continue

        confidence = Confidence(
            score=min(1.0, (cylinder.confidence.score * 0.8) + 0.2),
            reasons=[
                "cylinder axis through stock face pair",
                f"hole radius {cylinder.radius:.4f}",
                f"hole length {hole_length:.4f}",
            ],
        )

        holes.append(
            ThroughHoleFeature(
                kind=FeatureKind.THROUGH_HOLE,
                confidence=confidence,
                parameters={
                    "center_xy": entry_xy,
                    "radius": cylinder.radius,
                    "depth": hole_length,
                    "axis_origin": tuple(float(x) for x in entry_pt.tolist()),
                    "axis_direction": tuple(float(x) for x in axis_direction.tolist()),
                },
                references={},
                center_xy=entry_xy,
                radius=float(cylinder.radius),
                depth=hole_length,
                axis_origin=tuple(float(x) for x in entry_pt.tolist()),
                axis_direction=tuple(float(x) for x in axis_direction.tolist()),
            )
        )

    deduplicated = _deduplicate_holes(holes, tolerances)
    return _select_plausible_hole_family(
        holes=deduplicated,
        profile_loop=profile_loop,
        base_extrude=base_extrude,
        tolerances=tolerances,
    )


def _infer_blind_holes(
    cylinder_primitives: list[CylinderPrimitive],
    base_extrude: BaseExtrudeFeature,
    through_holes: list[ThroughHoleFeature],
    tolerances: ToleranceConfig,
) -> list[BlindHoleFeature]:
    """Shorter aligned cylinders inside the stock footprint: counterbores / blind holes."""
    extrusion_axis = np.asarray(base_extrude.sketch_plane["z_dir"], dtype=np.float64)
    basis_x = np.asarray(base_extrude.sketch_plane["x_dir"], dtype=np.float64)
    basis_y = np.asarray(base_extrude.sketch_plane["y_dir"], dtype=np.float64)
    origin = np.asarray(base_extrude.sketch_plane["origin"], dtype=np.float64)
    profile_loop = base_extrude.profile_loops[0]
    depth = float(base_extrude.depth)

    blinds: list[BlindHoleFeature] = []
    for cylinder in cylinder_primitives:
        h = cylinder.height_estimate
        if h is None:
            continue
        if h >= depth * _THROUGH_CYLINDER_MIN_DEPTH_RATIO:
            continue
        if h < depth * _BLIND_CYLINDER_MIN_DEPTH_RATIO or h > depth * _BLIND_CYLINDER_MAX_DEPTH_RATIO:
            continue

        axis_origin = np.asarray(cylinder.axis_origin, dtype=np.float64)
        axis_direction = np.asarray(cylinder.axis_direction, dtype=np.float64)
        axis_direction = axis_direction / max(np.linalg.norm(axis_direction), 1e-12)

        offset = axis_origin - origin
        t_ax = float(np.dot(offset, extrusion_axis))
        if t_ax + h * 0.52 > depth + tolerances.linear * 2.0:
            continue
        if t_ax - h * 0.52 < -tolerances.linear * 2.0:
            continue

        center_xy = (float(np.dot(offset, basis_x)), float(np.dot(offset, basis_y)))

        if not _hole_fits_profile(
            center_xy=center_xy,
            radius=cylinder.radius,
            profile_loop=profile_loop,
            tolerances=tolerances,
        ):
            continue

        if _matches_any_hole_center(
            center_xy,
            cylinder.radius,
            through_holes,
            tolerances,
        ):
            continue

        hole_depth = float(
            min(
                max(h * 1.08 + tolerances.linear * 2.0, tolerances.linear * 5.0),
                depth * 0.94,
            )
        )
        if hole_depth < float(cylinder.radius) * 1.05:
            continue

        confidence = Confidence(
            score=min(1.0, (cylinder.confidence.score * 0.72) + 0.12),
            reasons=[
                "cylinder shorter than stock thickness",
                f"blind hole depth {hole_depth:.4f}",
                f"radius {cylinder.radius:.4f}",
            ],
        )
        blinds.append(
            BlindHoleFeature(
                kind=FeatureKind.BLIND_HOLE,
                confidence=confidence,
                parameters={
                    "center_xy": center_xy,
                    "radius": cylinder.radius,
                    "hole_depth": hole_depth,
                    "axis_origin": tuple(float(x) for x in axis_origin.tolist()),
                    "axis_direction": tuple(float(x) for x in axis_direction.tolist()),
                },
                references={},
                center_xy=center_xy,
                radius=float(cylinder.radius),
                hole_depth=hole_depth,
                axis_origin=tuple(float(x) for x in axis_origin.tolist()),
                axis_direction=tuple(float(x) for x in axis_direction.tolist()),
            )
        )

    return _deduplicate_blind_holes(blinds, tolerances)


def _matches_any_hole_center(
    center_xy: tuple[float, float],
    radius: float,
    through_holes: list[ThroughHoleFeature],
    tolerances: ToleranceConfig,
) -> bool:
    for hole in through_holes:
        center_delta = math.dist(center_xy, hole.center_xy)
        if center_delta <= max(tolerances.linear * 4.0, radius * 0.35, hole.radius * 0.35):
            return True
    return False


def _deduplicate_blind_holes(
    holes: list[BlindHoleFeature],
    tolerances: ToleranceConfig,
) -> list[BlindHoleFeature]:
    deduplicated: list[BlindHoleFeature] = []
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


def _infer_planar_pockets(
    plane_primitives: list[PlanePrimitive],
    base_extrude: BaseExtrudeFeature,
    cloud: SampledCloud,
    tolerances: ToleranceConfig,
) -> list[PocketFeature]:
    """Shallow voids from two small interior parallel planes (opposing normals) along extrusion."""
    z_dir = np.asarray(base_extrude.sketch_plane["z_dir"], dtype=np.float64)
    z_dir = z_dir / max(np.linalg.norm(z_dir), 1e-12)
    basis_x = np.asarray(base_extrude.sketch_plane["x_dir"], dtype=np.float64)
    basis_y = np.asarray(base_extrude.sketch_plane["y_dir"], dtype=np.float64)
    origin = np.asarray(base_extrude.sketch_plane["origin"], dtype=np.float64)
    depth = float(base_extrude.depth)
    profile_loop = base_extrude.profile_loops[0]
    profile_area = abs(_signed_polygon_area(profile_loop))
    if profile_area <= 1e-9:
        return []

    max_pocket_plane_area = profile_area * 0.42
    min_gap = depth * 0.055
    max_gap = min(depth * 0.48, depth * 0.92)
    edge_tol = max(tolerances.linear * 3.0, depth * 0.04)

    slabs: list[tuple[PlanePrimitive, float]] = []
    for plane in plane_primitives:
        cos_align = abs(float(np.dot(plane.normal, z_dir)))
        if cos_align < math.cos(math.radians(tolerances.angular_deg * 3.0)):
            continue
        t = float(np.dot(plane.origin - origin, z_dir))
        if t <= edge_tol or t >= depth - edge_tol:
            continue
        a = float(plane.region.area)
        if a > max_pocket_plane_area or a < max(tolerances.min_region_area * 0.45, profile_area * 0.004):
            continue
        slabs.append((plane, t))

    slabs.sort(key=lambda item: item[1])
    pockets: list[PocketFeature] = []
    used_pairs: set[tuple[int, int]] = set()

    for i in range(len(slabs)):
        for j in range(i + 1, len(slabs)):
            p0, t0 = slabs[i]
            p1, t1 = slabs[j]
            key = (i, j)
            if key in used_pairs:
                continue
            gap = t1 - t0
            if gap < min_gap or gap > max_gap:
                continue
            if float(np.dot(p0.normal, p1.normal)) > -0.42:
                continue

            idx = sorted(set(p0.region.point_indices) | set(p1.region.point_indices))
            if len(idx) < 4:
                continue
            pts = np.asarray(cloud.points[idx], dtype=np.float64)
            local_x = (pts - origin) @ basis_x
            local_y = (pts - origin) @ basis_y
            try:
                loop_2d = _convex_profile_loop(np.column_stack((local_x, local_y)))
            except Exception:
                continue
            pocket_area = abs(_signed_polygon_area(loop_2d))
            if pocket_area > profile_area * 0.55 or pocket_area < tolerances.min_region_area * 0.08:
                continue
            centroid = (float(np.mean(local_x)), float(np.mean(local_y)))
            if not _point_in_polygon(centroid, profile_loop):
                continue
            if _point_to_polygon_edges_distance(centroid, profile_loop) < max(
                tolerances.linear * 2.0,
                0.05 * math.sqrt(max(pocket_area, 1e-12)),
            ):
                continue

            pocket_depth = float(min(gap * 1.04 + tolerances.linear, depth * 0.9))
            confidence = Confidence(
                score=0.62,
                reasons=[
                    "interior parallel pocket faces",
                    f"pocket_depth {pocket_depth:.4f}",
                ],
            )
            pockets.append(
                PocketFeature(
                    kind=FeatureKind.POCKET,
                    confidence=confidence,
                    parameters={"pocket_depth": pocket_depth},
                    references={},
                    profile_loop=loop_2d,
                    pocket_depth=pocket_depth,
                )
            )
            used_pairs.add(key)
            used_pairs.add((j, i))
            if len(pockets) >= 2:
                return pockets

    return pockets


def _infer_bosses(
    cylinder_primitives: list[CylinderPrimitive],
    base_extrude: BaseExtrudeFeature,
    tolerances: ToleranceConfig,
    *,
    reserved_hole_centers: list[tuple[tuple[float, float], float]] | None = None,
) -> list[BossFeature]:
    extrusion_axis = np.asarray(base_extrude.sketch_plane["z_dir"], dtype=np.float64)
    basis_x = np.asarray(base_extrude.sketch_plane["x_dir"], dtype=np.float64)
    basis_y = np.asarray(base_extrude.sketch_plane["y_dir"], dtype=np.float64)
    origin = np.asarray(base_extrude.sketch_plane["origin"], dtype=np.float64)
    max_height = max(base_extrude.depth * _THROUGH_CYLINDER_MIN_DEPTH_RATIO, tolerances.linear * 3.0)

    bosses: list[BossFeature] = []
    for cylinder in cylinder_primitives:
        alignment = abs(float(np.dot(cylinder.axis_direction, extrusion_axis)))
        if alignment < math.cos(math.radians(tolerances.angular_deg * 2.0)):
            continue
        if cylinder.height_estimate is None:
            continue
        if cylinder.height_estimate >= max_height:
            continue

        offset = np.asarray(cylinder.axis_origin, dtype=np.float64) - origin
        center_xy = (float(np.dot(offset, basis_x)), float(np.dot(offset, basis_y)))
        if reserved_hole_centers:
            skip_reserved = False
            for reserved_xy, reserved_r in reserved_hole_centers:
                if math.dist(center_xy, reserved_xy) <= max(
                    tolerances.linear * 3.0,
                    cylinder.radius * 0.35,
                    reserved_r * 0.35,
                ):
                    skip_reserved = True
                    break
            if skip_reserved:
                continue

        axial_offset = float(np.dot(offset, extrusion_axis))
        if axial_offset < (-tolerances.linear * 2.0) or axial_offset > (base_extrude.depth + tolerances.linear * 2.0):
            continue
        start_offset = 0.0 if axial_offset <= (base_extrude.depth * 0.5) else base_extrude.depth

        confidence = Confidence(
            score=min(1.0, (cylinder.confidence.score * 0.75) + 0.15),
            reasons=[
                "cylinder axis aligned to extrusion axis",
                f"boss radius {cylinder.radius:.4f}",
                f"boss height {cylinder.height_estimate:.4f}",
            ],
        )
        bosses.append(
            BossFeature(
                kind=FeatureKind.BOSS,
                confidence=confidence,
                parameters={
                    "center_xy": center_xy,
                    "radius": cylinder.radius,
                    "height": cylinder.height_estimate,
                    "start_offset": start_offset,
                },
                references={},
                center_xy=center_xy,
                radius=cylinder.radius,
                height=float(cylinder.height_estimate),
                start_offset=float(start_offset),
            )
        )

    return _deduplicate_bosses(bosses, tolerances)


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

    if np.median([hole.radius for hole in selected_family]) > max(
        base_extrude.depth * _THROUGH_CYLINDER_MIN_DEPTH_RATIO,
        tolerances.linear * 4.0,
    ):
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


def _deduplicate_bosses(
    bosses: list[BossFeature],
    tolerances: ToleranceConfig,
) -> list[BossFeature]:
    deduplicated: list[BossFeature] = []
    for boss in sorted(
        bosses,
        key=lambda item: (item.center_xy[0], item.center_xy[1], item.radius, item.start_offset),
    ):
        duplicate = False
        for existing in deduplicated:
            center_delta = math.dist(boss.center_xy, existing.center_xy)
            radius_delta = abs(boss.radius - existing.radius)
            height_delta = abs(boss.height - existing.height)
            if (
                center_delta <= max(tolerances.linear * 2.0, boss.radius * 0.2)
                and radius_delta <= max(tolerances.linear * 2.0, boss.radius * 0.1)
                and height_delta <= max(tolerances.linear * 2.0, boss.height * 0.2)
            ):
                duplicate = True
                break
        if not duplicate:
            deduplicated.append(boss)
    return deduplicated


def _deduplicate_countersinks(
    countersinks: list[CounterSinkHoleFeature],
    tolerances: ToleranceConfig,
) -> list[CounterSinkHoleFeature]:
    deduplicated: list[CounterSinkHoleFeature] = []
    for countersink in sorted(
        countersinks,
        key=lambda item: (
            item.center_xy[0],
            item.center_xy[1],
            item.hole_radius,
            item.counter_sink_radius,
        ),
    ):
        duplicate = False
        for existing in deduplicated:
            center_delta = math.dist(countersink.center_xy, existing.center_xy)
            hole_delta = abs(countersink.hole_radius - existing.hole_radius)
            sink_delta = abs(countersink.counter_sink_radius - existing.counter_sink_radius)
            if (
                center_delta <= max(tolerances.linear * 2.0, countersink.hole_radius * 0.2)
                and hole_delta <= max(tolerances.linear * 2.0, countersink.hole_radius * 0.1)
                and sink_delta <= max(tolerances.linear * 2.0, countersink.counter_sink_radius * 0.1)
            ):
                duplicate = True
                break
        if not duplicate:
            deduplicated.append(countersink)
    return deduplicated


def _deduplicate_spherical_bosses(
    bosses: list[SphericalBossFeature],
    tolerances: ToleranceConfig,
) -> list[SphericalBossFeature]:
    deduplicated: list[SphericalBossFeature] = []
    for boss in sorted(bosses, key=lambda item: (item.center_xy[0], item.center_xy[1], item.center_offset, item.radius)):
        duplicate = False
        for existing in deduplicated:
            if (
                math.dist(boss.center_xy, existing.center_xy) <= max(tolerances.linear * 2.0, boss.radius * 0.2)
                and abs(boss.center_offset - existing.center_offset) <= max(tolerances.linear * 2.0, boss.radius * 0.2)
                and abs(boss.radius - existing.radius) <= max(tolerances.linear * 2.0, boss.radius * 0.1)
            ):
                duplicate = True
                break
        if not duplicate:
            deduplicated.append(boss)
    return deduplicated


def _deduplicate_spherical_cavities(
    cavities: list[SphericalCavityFeature],
    tolerances: ToleranceConfig,
) -> list[SphericalCavityFeature]:
    deduplicated: list[SphericalCavityFeature] = []
    for cavity in sorted(cavities, key=lambda item: (item.center_xy[0], item.center_xy[1], item.center_offset, item.radius)):
        duplicate = False
        for existing in deduplicated:
            if (
                math.dist(cavity.center_xy, existing.center_xy) <= max(tolerances.linear * 2.0, cavity.radius * 0.2)
                and abs(cavity.center_offset - existing.center_offset) <= max(tolerances.linear * 2.0, cavity.radius * 0.2)
                and abs(cavity.radius - existing.radius) <= max(tolerances.linear * 2.0, cavity.radius * 0.1)
            ):
                duplicate = True
                break
        if not duplicate:
            deduplicated.append(cavity)
    return deduplicated
