from __future__ import annotations

import math

from mesh2cad.domain.features import (
    BaseExtrudeFeature,
    BlindHoleFeature,
    BossFeature,
    CounterSinkHoleFeature,
    Feature,
    HoleSection,
    HoleStackFeature,
    PocketFeature,
    RevolveSolidFeature,
    SphericalBossFeature,
    SphericalCavityFeature,
    ThroughHoleFeature,
)
from mesh2cad.domain.types import FeatureKind, HoleSectionKind, HoleTermination
from mesh2cad.cad.vector_utils import (
    format_tuple3,
    revolve_sketch_frame,
    sketch_plane_vectors,
)


def _is_hole_axis_aligned(axis_direction: tuple[float, float, float], z_dir: tuple[float, float, float]) -> bool:
    if axis_direction is None or z_dir is None:
        return True
    return (
        abs(axis_direction[0] - z_dir[0]) <= 1e-6
        and abs(axis_direction[1] - z_dir[1]) <= 1e-6
        and abs(axis_direction[2] - z_dir[2]) <= 1e-6
    )


def generate_script(features: list[Feature]) -> str:
    """Generate a narrow build123d script for the currently supported feature set.

    This includes base extrusion, aligned through-holes, angled through-hole support
    by generating dedicated sketch planes for non-aligned cylinder axes, and angled
    countersink support for countersinks matched to angled holes.
    """
    revolve_feature = next((feature for feature in features if isinstance(feature, RevolveSolidFeature)), None)
    base_feature = next(
        (feature for feature in features if isinstance(feature, BaseExtrudeFeature)),
        None,
    )

    if revolve_feature is not None and base_feature is None:
        return _generate_revolve_script(revolve_feature)

    if base_feature is None:
        raise ValueError("A BaseExtrudeFeature or RevolveSolidFeature is required to generate a CAD script.")

    hole_stacks = [feature for feature in features if isinstance(feature, HoleStackFeature)]
    through_holes = [feature for feature in features if isinstance(feature, ThroughHoleFeature)]
    countersink_holes = [feature for feature in features if isinstance(feature, CounterSinkHoleFeature)]
    spherical_bosses = [feature for feature in features if isinstance(feature, SphericalBossFeature)]
    spherical_cavities = [feature for feature in features if isinstance(feature, SphericalCavityFeature)]
    blind_holes = [feature for feature in features if isinstance(feature, BlindHoleFeature)]
    pockets = [feature for feature in features if isinstance(feature, PocketFeature)]
    bosses = [feature for feature in features if isinstance(feature, BossFeature)]
    counterbore_holes: list[
        tuple[
            tuple[float, float],
            float,
            float,
            float,
            bool,
            tuple[float, float, float],
            tuple[float, float, float],
            float | None,
        ]
    ] = []

    if hole_stacks:
        through_holes, blind_holes, countersink_holes, counterbore_holes = _decompose_hole_stacks(hole_stacks)

    profile_loop = _normalize_profile_loop(base_feature.profile_loops[0])
    lines: list[str] = [
        "from build123d import BuildPart, BuildSketch, Plane, Polygon, Circle, Locations, Mode, CounterBoreHole, CounterSinkHole, Sphere, extrude",
        "",
        f"DEPTH = {base_feature.depth:.6f}",
        "PROFILE = [",
    ]

    for x_coord, y_coord in profile_loop:
        lines.append(f"    ({x_coord:.6f}, {y_coord:.6f}),")
    lines.append("]")

    hole_plane_z_dir = None
    if isinstance(base_feature.sketch_plane, dict):
        hole_plane_z_dir = base_feature.sketch_plane.get("z_dir", (0.0, 0.0, 1.0))

    aligned_holes: list[ThroughHoleFeature] = []
    angled_holes: list[ThroughHoleFeature] = []
    for hole in through_holes:
        if _is_hole_axis_aligned(hole.axis_direction, hole_plane_z_dir):
            aligned_holes.append(hole)
        else:
            angled_holes.append(hole)

    if angled_holes:
        lines.append("ANGLED_HOLES = [")
        for hole in angled_holes:
            hole_origin = format_tuple3(hole.axis_origin)
            hole_direction = format_tuple3(hole.axis_direction)
            hole_x_dir = format_tuple3(revolve_sketch_frame(hole.axis_origin, hole.axis_direction)[2])
            lines.append(
                f"    ({hole_origin}, {hole_x_dir}, {hole_direction}, {hole.radius:.6f}, {hole.depth:.6f}),"
            )
        lines.append("]")
    else:
        lines.append("ANGLED_HOLES = []")

    if aligned_holes:
        lines.append("HOLES = [")
        for hole in aligned_holes:
            lines.append(
                f"    ({hole.center_xy[0]:.6f}, {hole.center_xy[1]:.6f}, {hole.radius:.6f}),"
            )
        lines.append("]")
    else:
        lines.append("HOLES = []")

    aligned_blind_holes: list[BlindHoleFeature] = []
    angled_blind_holes: list[BlindHoleFeature] = []
    for hole in blind_holes:
        if _is_hole_axis_aligned(hole.axis_direction, hole_plane_z_dir):
            aligned_blind_holes.append(hole)
        else:
            angled_blind_holes.append(hole)

    if angled_blind_holes:
        lines.append("ANGLED_BLIND_HOLES = [")
        for hole in angled_blind_holes:
            hole_origin = format_tuple3(hole.axis_origin)
            hole_direction = format_tuple3(hole.axis_direction)
            hole_x_dir = format_tuple3(revolve_sketch_frame(hole.axis_origin, hole.axis_direction)[2])
            lines.append(
                f"    ({hole_origin}, {hole_x_dir}, {hole_direction}, {hole.center_xy[0]:.6f}, {hole.center_xy[1]:.6f}, {hole.radius:.6f}, {hole.hole_depth:.6f}),"
            )
        lines.append("]")
    else:
        lines.append("ANGLED_BLIND_HOLES = []")

    if aligned_blind_holes:
        lines.append("BLIND_HOLES = [")
        for hole in aligned_blind_holes:
            lines.append(
                f"    ({hole.center_xy[0]:.6f}, {hole.center_xy[1]:.6f}, {hole.radius:.6f}, {hole.hole_depth:.6f}),"
            )
        lines.append("]")
    else:
        lines.append("BLIND_HOLES = []")

    aligned_countersinks: list[CounterSinkHoleFeature] = []
    angled_countersinks: list[CounterSinkHoleFeature] = []
    for sink in countersink_holes:
        if _is_hole_axis_aligned(sink.axis_direction, hole_plane_z_dir):
            aligned_countersinks.append(sink)
        else:
            angled_countersinks.append(sink)

    if angled_countersinks:
        lines.append("ANGLED_COUNTERSINKS = [")
        for sink in angled_countersinks:
            sink_origin = format_tuple3(sink.axis_origin)
            sink_direction = format_tuple3(sink.axis_direction)
            sink_x_dir = format_tuple3(revolve_sketch_frame(sink.axis_origin, sink.axis_direction)[2])
            lines.append(
                f"    ({sink_origin}, {sink_x_dir}, {sink_direction}, {sink.center_xy[0]:.6f}, {sink.center_xy[1]:.6f}, {sink.hole_radius:.6f}, {sink.counter_sink_radius:.6f}, {sink.counter_sink_angle_deg:.6f}, {str(bool(sink.start_from_top))}),"
            )
        lines.append("]")
    else:
        lines.append("ANGLED_COUNTERSINKS = []")

    if aligned_countersinks:
        lines.append("COUNTERSINK_HOLES = [")
        for hole in aligned_countersinks:
            lines.append(
                f"    ({hole.center_xy[0]:.6f}, {hole.center_xy[1]:.6f}, {hole.hole_radius:.6f}, {hole.counter_sink_radius:.6f}, {hole.counter_sink_angle_deg:.6f}, {str(bool(hole.start_from_top))}),"
            )
        lines.append("]")
    else:
        lines.append("COUNTERSINK_HOLES = []")

    aligned_counterbores: list[
        tuple[
            tuple[float, float],
            float,
            float,
            float,
            bool,
            tuple[float, float, float],
            tuple[float, float, float],
            float | None,
        ]
    ] = []
    angled_counterbores: list[
        tuple[
            tuple[float, float],
            float,
            float,
            float,
            bool,
            tuple[float, float, float],
            tuple[float, float, float],
            float | None,
        ]
    ] = []
    for counterbore in counterbore_holes:
        center_xy, bore_radius, hole_radius, bore_depth, start_from_top, axis_origin, axis_direction, total_depth = counterbore
        if _is_hole_axis_aligned(axis_direction, hole_plane_z_dir):
            aligned_counterbores.append(counterbore)
        else:
            angled_counterbores.append(counterbore)

    if angled_counterbores:
        lines.append("ANGLED_COUNTERBORES = [")
        for center_xy, bore_radius, hole_radius, bore_depth, start_from_top, axis_origin, axis_direction, total_depth in angled_counterbores:
            bore_origin = format_tuple3(axis_origin)
            bore_direction = format_tuple3(axis_direction)
            bore_x_dir = format_tuple3(revolve_sketch_frame(axis_origin, axis_direction)[2])
            depth_literal = "None" if total_depth is None else f"{float(total_depth):.6f}"
            lines.append(
                f"    ({bore_origin}, {bore_x_dir}, {bore_direction}, {center_xy[0]:.6f}, {center_xy[1]:.6f}, {hole_radius:.6f}, {bore_radius:.6f}, {bore_depth:.6f}, {str(bool(start_from_top))}, {depth_literal}),"
            )
        lines.append("]")
    else:
        lines.append("ANGLED_COUNTERBORES = []")

    if aligned_counterbores:
        lines.append("COUNTERBORE_HOLES = [")
        for center_xy, bore_radius, hole_radius, bore_depth, start_from_top, axis_origin, axis_direction, total_depth in aligned_counterbores:
            depth_literal = "None" if total_depth is None else f"{float(total_depth):.6f}"
            lines.append(
                f"    ({center_xy[0]:.6f}, {center_xy[1]:.6f}, {hole_radius:.6f}, {bore_radius:.6f}, {bore_depth:.6f}, {str(bool(start_from_top))}, {depth_literal}),"
            )
        lines.append("]")
    else:
        lines.append("COUNTERBORE_HOLES = []")

    if spherical_bosses:
        lines.append("SPHERICAL_BOSSES = [")
        for boss in spherical_bosses:
            lines.append(
                f"    ({boss.center_xy[0]:.6f}, {boss.center_xy[1]:.6f}, {boss.center_offset:.6f}, {boss.radius:.6f}),"
            )
        lines.append("]")
    else:
        lines.append("SPHERICAL_BOSSES = []")

    if spherical_cavities:
        lines.append("SPHERICAL_CAVITIES = [")
        for cavity in spherical_cavities:
            lines.append(
                f"    ({cavity.center_xy[0]:.6f}, {cavity.center_xy[1]:.6f}, {cavity.center_offset:.6f}, {cavity.radius:.6f}),"
            )
        lines.append("]")
    else:
        lines.append("SPHERICAL_CAVITIES = []")

    if pockets:
        lines.append("POCKETS = [")
        for pocket in pockets:
            loop = _normalize_profile_loop(pocket.profile_loop)
            inner = ", ".join(f"({x:.6f}, {y:.6f})" for x, y in loop)
            lines.append(f"    ([{inner}], {pocket.pocket_depth:.6f}),")
        lines.append("]")
    else:
        lines.append("POCKETS = []")

    if bosses:
        lines.append("BOSSES = [")
        for boss in bosses:
            lines.append(
                f"    ({boss.center_xy[0]:.6f}, {boss.center_xy[1]:.6f}, {boss.radius:.6f}, {boss.height:.6f}, {boss.start_offset:.6f}),"
            )
        lines.append("]")
    else:
        lines.append("BOSSES = []")

    sketch_block = _extrude_sketch_block(base_feature)
    lines.extend(sketch_block)

    if angled_holes:
        lines.extend(
            [
                "    for hole_origin, hole_x_dir, hole_axis, radius, depth in ANGLED_HOLES:",
                "        HOLE_PLANE = Plane(origin=hole_origin, x_dir=hole_x_dir, z_dir=hole_axis)",
                "        with BuildSketch(HOLE_PLANE):",
                "            Circle(radius, mode=Mode.SUBTRACT)",
                "        extrude(amount=depth, mode=Mode.SUBTRACT)",
            ]
        )

    if angled_countersinks:
        lines.extend(
            [
                "    for sink_origin, sink_x_dir, sink_axis, x_pos, y_pos, hole_radius, sink_radius, sink_angle, start_from_top in ANGLED_COUNTERSINKS:",
                "        SINK_PLANE = Plane(origin=sink_origin, x_dir=sink_x_dir, z_dir=sink_axis)",
                "        with Locations(SINK_PLANE):",
                "            with Locations((x_pos, y_pos)):",
                "                CounterSinkHole(radius=hole_radius, counter_sink_radius=sink_radius, depth=None, counter_sink_angle=sink_angle, mode=Mode.SUBTRACT)",
            ]
        )

    if angled_blind_holes:
        lines.extend(
            [
                "    for blind_origin, blind_x_dir, blind_axis, x_pos, y_pos, radius, h_depth in ANGLED_BLIND_HOLES:",
                "        BLIND_PLANE = Plane(origin=blind_origin, x_dir=blind_x_dir, z_dir=blind_axis)",
                "        with BuildSketch(BLIND_PLANE):",
                "            with Locations((x_pos, y_pos)):",
                "                Circle(radius)",
                "        extrude(amount=h_depth, mode=Mode.SUBTRACT)",
            ]
        )

    if angled_counterbores:
        lines.extend(
            [
                "    for bore_origin, bore_x_dir, bore_axis, x_pos, y_pos, hole_radius, bore_radius, bore_depth, start_from_top, total_depth in ANGLED_COUNTERBORES:",
                "        BORE_PLANE = Plane(origin=bore_origin, x_dir=bore_x_dir, z_dir=bore_axis)",
                "        with Locations(BORE_PLANE):",
                "            with Locations((x_pos, y_pos)):",
                "                CounterBoreHole(radius=hole_radius, counter_bore_radius=bore_radius, counter_bore_depth=bore_depth, depth=total_depth, mode=Mode.SUBTRACT)",
            ]
        )

    return "\n".join(lines)


def _extrude_sketch_block(base_feature: BaseExtrudeFeature) -> list[str]:
    sp = base_feature.sketch_plane
    if isinstance(sp, dict) and all(k in sp for k in ("origin", "x_dir", "z_dir")):
        origin, x_dir, y_dir, z_dir = sketch_plane_vectors(sp)
        return [
            "",
            f"ORIGIN = {format_tuple3(origin)}",
            f"X_DIR = {format_tuple3(x_dir)}",
            f"Y_DIR = {format_tuple3(y_dir)}",
            f"Z_DIR = {format_tuple3(z_dir)}",
            "NEG_Z_DIR = (-Z_DIR[0], -Z_DIR[1], -Z_DIR[2])",
            "SKETCH_PLANE = Plane(origin=ORIGIN, x_dir=X_DIR, z_dir=Z_DIR)",
            "",
            "with BuildPart() as part:",
            "    with BuildSketch(SKETCH_PLANE) as profile:",
            "        Polygon(*PROFILE)",
            "        for x_pos, y_pos, radius in HOLES:",
            "            with Locations((x_pos, y_pos)):",
            "                Circle(radius, mode=Mode.SUBTRACT)",
            "    extrude(amount=DEPTH)",
            "    for x_pos, y_pos, radius, height, start_offset in BOSSES:",
            "        boss_origin = (",
            "            ORIGIN[0] + (Z_DIR[0] * start_offset),",
            "            ORIGIN[1] + (Z_DIR[1] * start_offset),",
            "            ORIGIN[2] + (Z_DIR[2] * start_offset),",
            "        )",
            "        boss_plane = Plane(origin=boss_origin, x_dir=X_DIR, z_dir=Z_DIR)",
            "        with BuildSketch(boss_plane):",
            "            with Locations((x_pos, y_pos)):",
            "                Circle(radius)",
            "        extrude(amount=height)",
            "    for x_pos, y_pos, z_pos, radius in SPHERICAL_BOSSES:",
            "        sphere_center = (",
            "            ORIGIN[0] + (X_DIR[0] * x_pos) + (Y_DIR[0] * y_pos) + (Z_DIR[0] * z_pos),",
            "            ORIGIN[1] + (X_DIR[1] * x_pos) + (Y_DIR[1] * y_pos) + (Z_DIR[1] * z_pos),",
            "            ORIGIN[2] + (X_DIR[2] * x_pos) + (Y_DIR[2] * y_pos) + (Z_DIR[2] * z_pos),",
            "        )",
            "        with Locations(sphere_center):",
            "            Sphere(radius, mode=Mode.ADD)",
            "    for x_pos, y_pos, z_pos, radius in SPHERICAL_CAVITIES:",
            "        sphere_center = (",
            "            ORIGIN[0] + (X_DIR[0] * x_pos) + (Y_DIR[0] * y_pos) + (Z_DIR[0] * z_pos),",
            "            ORIGIN[1] + (X_DIR[1] * x_pos) + (Y_DIR[1] * y_pos) + (Z_DIR[1] * z_pos),",
            "            ORIGIN[2] + (X_DIR[2] * x_pos) + (Y_DIR[2] * y_pos) + (Z_DIR[2] * z_pos),",
            "        )",
            "        with Locations(sphere_center):",
            "            Sphere(radius, mode=Mode.SUBTRACT)",
            "    for x_pos, y_pos, radius, h_depth in BLIND_HOLES:",
            "        top_origin = (",
            "            ORIGIN[0] + (Z_DIR[0] * DEPTH),",
            "            ORIGIN[1] + (Z_DIR[1] * DEPTH),",
            "            ORIGIN[2] + (Z_DIR[2] * DEPTH),",
            "        )",
            "        top_plane = Plane(origin=top_origin, x_dir=X_DIR, z_dir=NEG_Z_DIR)",
            "        with BuildSketch(top_plane):",
            "            with Locations((x_pos, y_pos)):",
            "                Circle(radius)",
            "        extrude(amount=h_depth, mode=Mode.SUBTRACT)",
            "    for x_pos, y_pos, hole_radius, sink_radius, sink_angle, start_from_top in COUNTERSINK_HOLES:",
            "        if start_from_top:",
            "            sink_origin = (",
            "                ORIGIN[0] + (Z_DIR[0] * DEPTH),",
            "                ORIGIN[1] + (Z_DIR[1] * DEPTH),",
            "                ORIGIN[2] + (Z_DIR[2] * DEPTH),",
            "            )",
            "            sink_plane = Plane(origin=sink_origin, x_dir=X_DIR, z_dir=NEG_Z_DIR)",
            "        else:",
            "            sink_plane = SKETCH_PLANE",
            "        with Locations(sink_plane):",
            "            with Locations((x_pos, y_pos)):",
            "                CounterSinkHole(radius=hole_radius, counter_sink_radius=sink_radius, depth=None, counter_sink_angle=sink_angle, mode=Mode.SUBTRACT)",
            "    for x_pos, y_pos, hole_radius, bore_radius, bore_depth, start_from_top, total_depth in COUNTERBORE_HOLES:",
            "        if start_from_top:",
            "            bore_origin = (",
            "                ORIGIN[0] + (Z_DIR[0] * DEPTH),",
            "                ORIGIN[1] + (Z_DIR[1] * DEPTH),",
            "                ORIGIN[2] + (Z_DIR[2] * DEPTH),",
            "            )",
            "            bore_plane = Plane(origin=bore_origin, x_dir=X_DIR, z_dir=NEG_Z_DIR)",
            "        else:",
            "            bore_plane = SKETCH_PLANE",
            "        with Locations(bore_plane):",
            "            with Locations((x_pos, y_pos)):",
            "                CounterBoreHole(radius=hole_radius, counter_bore_radius=bore_radius, counter_bore_depth=bore_depth, depth=total_depth, mode=Mode.SUBTRACT)",
            "    for pocket_profile, pocket_depth in POCKETS:",
            "        top_origin = (",
            "            ORIGIN[0] + (Z_DIR[0] * DEPTH),",
            "            ORIGIN[1] + (Z_DIR[1] * DEPTH),",
            "            ORIGIN[2] + (Z_DIR[2] * DEPTH),",
            "        )",
            "        top_plane = Plane(origin=top_origin, x_dir=X_DIR, z_dir=NEG_Z_DIR)",
            "        with BuildSketch(top_plane):",
            "            Polygon(*pocket_profile)",
            "        extrude(amount=pocket_depth, mode=Mode.SUBTRACT)",
            "",
            "result = part.part",
        ]

    return [
        "",
        "with BuildPart() as part:",
        "    with BuildSketch() as profile:",
        "        Polygon(*PROFILE)",
        "        for x_pos, y_pos, radius in HOLES:",
        "            with Locations((x_pos, y_pos)):",
        "                Circle(radius, mode=Mode.SUBTRACT)",
        "    extrude(amount=DEPTH)",
        "    for x_pos, y_pos, radius, height, start_offset in BOSSES:",
        "        with BuildSketch():",
        "            with Locations((x_pos, y_pos)):",
        "                Circle(radius)",
        "        extrude(amount=height)",
        "    for x_pos, y_pos, z_pos, radius in SPHERICAL_BOSSES:",
        "        with Locations((x_pos, y_pos, z_pos)):",
        "            Sphere(radius, mode=Mode.ADD)",
        "    for x_pos, y_pos, z_pos, radius in SPHERICAL_CAVITIES:",
        "        with Locations((x_pos, y_pos, z_pos)):",
        "            Sphere(radius, mode=Mode.SUBTRACT)",
        "    for x_pos, y_pos, radius, h_depth in BLIND_HOLES:",
        "        with BuildSketch():",
        "            with Locations((x_pos, y_pos)):",
        "                Circle(radius)",
        "        extrude(amount=h_depth, mode=Mode.SUBTRACT)",
        "    for x_pos, y_pos, hole_radius, sink_radius, sink_angle, start_from_top in COUNTERSINK_HOLES:",
        "        with Locations((x_pos, y_pos)):",
        "            CounterSinkHole(radius=hole_radius, counter_sink_radius=sink_radius, depth=None, counter_sink_angle=sink_angle, mode=Mode.SUBTRACT)",
        "    for x_pos, y_pos, hole_radius, bore_radius, bore_depth, start_from_top, total_depth in COUNTERBORE_HOLES:",
        "        with Locations((x_pos, y_pos)):",
        "            CounterBoreHole(radius=hole_radius, counter_bore_radius=bore_radius, counter_bore_depth=bore_depth, depth=total_depth, mode=Mode.SUBTRACT)",
        "    for pocket_profile, pocket_depth in POCKETS:",
        "        with BuildSketch():",
        "            Polygon(*pocket_profile)",
        "        extrude(amount=pocket_depth, mode=Mode.SUBTRACT)",
        "",
        "result = part.part",
    ]


def _generate_revolve_script(feature: RevolveSolidFeature) -> str:
    """Profile in sketch (radial, axial); revolution about axis through origin (pose-aware)."""
    profile = feature.profile_rz if feature.profile_rz else [
        (0.0, -feature.height / 2.0),
        (feature.radius, -feature.height / 2.0),
        (feature.radius, feature.height / 2.0),
        (0.0, feature.height / 2.0),
    ]
    o, u, x_rad, y_norm = revolve_sketch_frame(feature.axis_origin, feature.axis_direction)

    lines: list[str] = [
        "from build123d import BuildPart, BuildSketch, Plane, Axis, Polygon, revolve",
        "",
        f"ORIGIN = {format_tuple3(o)}",
        f"AXIS_DIR = {format_tuple3(u)}",
        f"X_RADIAL = {format_tuple3(x_rad)}",
        f"Y_NORMAL = {format_tuple3(y_norm)}",
        "REVOLVE_PLANE = Plane(origin=ORIGIN, x_dir=X_RADIAL, z_dir=Y_NORMAL)",
        "PROFILE = [",
    ]
    for r_coord, z_coord in profile:
        lines.append(f"    ({r_coord:.6f}, {z_coord:.6f}),")
    lines.extend(
        [
            "]",
            "",
            "with BuildPart() as part:",
            "    with BuildSketch(REVOLVE_PLANE):",
            "        Polygon(*PROFILE)",
            "    revolve(axis=Axis(ORIGIN, AXIS_DIR), revolution_arc=360.0)",
            "",
            "result = part.part",
        ]
    )
    return "\n".join(lines)


def _normalize_profile_loop(profile_loop: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(profile_loop) < 3:
        raise ValueError("Base extrusion profile must contain at least three points.")
    return profile_loop


def _decompose_hole_stacks(
    hole_stacks: list[HoleStackFeature],
) -> tuple[
    list[ThroughHoleFeature],
    list[BlindHoleFeature],
    list[CounterSinkHoleFeature],
    list[
        tuple[
            tuple[float, float],
            float,
            float,
            float,
            bool,
            tuple[float, float, float],
            tuple[float, float, float],
            float | None,
        ]
    ],
]:
    through_holes: list[ThroughHoleFeature] = []
    blind_holes: list[BlindHoleFeature] = []
    countersinks: list[CounterSinkHoleFeature] = []
    counterbores: list[
        tuple[
            tuple[float, float],
            float,
            float,
            float,
            bool,
            tuple[float, float, float],
            tuple[float, float, float],
            float | None,
        ]
    ] = []

    for stack in hole_stacks:
        if not stack.sections:
            continue

        if _stack_is_countersink(stack):
            cone_section, cylinder_section = stack.sections
            countersinks.append(
                CounterSinkHoleFeature(
                    kind=FeatureKind.COUNTERSINK_HOLE,
                    confidence=stack.confidence,
                    parameters=dict(stack.parameters),
                    references=dict(stack.references),
                    center_xy=stack.center_xy,
                    hole_radius=float(cylinder_section.start_radius),
                    counter_sink_radius=float(cone_section.start_radius),
                    counter_sink_angle_deg=_cone_angle_deg(cone_section),
                    start_from_top=bool(stack.start_from_top),
                    axis_origin=stack.axis_origin,
                    axis_direction=stack.axis_direction,
                )
            )
            continue

        if _stack_is_counterbore(stack):
            bore_section, hole_section = stack.sections
            counterbores.append(
                (
                    stack.center_xy,
                    float(bore_section.start_radius),
                    float(hole_section.start_radius),
                    float(bore_section.end_offset - bore_section.start_offset),
                    bool(stack.start_from_top),
                    stack.axis_origin,
                    stack.axis_direction,
                    None if stack.termination == HoleTermination.THROUGH else float(stack.total_depth),
                )
            )
            continue

        if _stack_is_single_cylindrical(stack, HoleTermination.THROUGH):
            section = stack.sections[0]
            through_holes.append(
                ThroughHoleFeature(
                    kind=FeatureKind.THROUGH_HOLE,
                    confidence=stack.confidence,
                    parameters=dict(stack.parameters),
                    references=dict(stack.references),
                    center_xy=stack.center_xy,
                    radius=float(section.start_radius),
                    depth=float(stack.total_depth),
                    axis_origin=stack.axis_origin,
                    axis_direction=stack.axis_direction,
                )
            )
            continue

        if _stack_is_single_cylindrical(stack, HoleTermination.BLIND):
            section = stack.sections[0]
            blind_holes.append(
                BlindHoleFeature(
                    kind=FeatureKind.BLIND_HOLE,
                    confidence=stack.confidence,
                    parameters=dict(stack.parameters),
                    references=dict(stack.references),
                    center_xy=stack.center_xy,
                    radius=float(section.start_radius),
                    hole_depth=float(stack.total_depth),
                    axis_origin=stack.axis_origin,
                    axis_direction=stack.axis_direction,
                )
            )

    return through_holes, blind_holes, countersinks, counterbores


def _stack_is_single_cylindrical(stack: HoleStackFeature, termination: HoleTermination) -> bool:
    return (
        stack.termination == termination
        and len(stack.sections) == 1
        and stack.sections[0].kind == HoleSectionKind.CYLINDER
        and abs(stack.sections[0].start_radius - stack.sections[0].end_radius) <= 1e-9
    )


def _stack_is_countersink(stack: HoleStackFeature) -> bool:
    if stack.termination != HoleTermination.THROUGH or len(stack.sections) != 2:
        return False
    first, second = stack.sections
    return (
        first.kind == HoleSectionKind.CONE
        and second.kind == HoleSectionKind.CYLINDER
        and first.start_radius > first.end_radius
        and abs(first.end_radius - second.start_radius) <= 1e-6
        and abs(second.start_radius - second.end_radius) <= 1e-6
    )


def _stack_is_counterbore(stack: HoleStackFeature) -> bool:
    if len(stack.sections) != 2:
        return False
    first, second = stack.sections
    return (
        first.kind == HoleSectionKind.CYLINDER
        and second.kind == HoleSectionKind.CYLINDER
        and abs(first.start_radius - first.end_radius) <= 1e-6
        and abs(second.start_radius - second.end_radius) <= 1e-6
        and first.start_radius > second.start_radius
        and first.end_offset <= second.start_offset + 1e-6
    )


def _cone_angle_deg(section: HoleSection) -> float:
    depth = max(section.end_offset - section.start_offset, 1e-9)
    radius_delta = max(section.start_radius - section.end_radius, 1e-9)
    return float(2.0 * math.degrees(math.atan(radius_delta / depth)))
