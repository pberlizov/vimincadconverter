from __future__ import annotations

from mesh2cad.domain.features import (
    BaseExtrudeFeature,
    BlindHoleFeature,
    BossFeature,
    CounterSinkHoleFeature,
    Feature,
    PocketFeature,
    RevolveSolidFeature,
    SphericalBossFeature,
    SphericalCavityFeature,
    ThroughHoleFeature,
)
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

    through_holes = [feature for feature in features if isinstance(feature, ThroughHoleFeature)]
    countersink_holes = [feature for feature in features if isinstance(feature, CounterSinkHoleFeature)]
    spherical_bosses = [feature for feature in features if isinstance(feature, SphericalBossFeature)]
    spherical_cavities = [feature for feature in features if isinstance(feature, SphericalCavityFeature)]
    blind_holes = [feature for feature in features if isinstance(feature, BlindHoleFeature)]
    pockets = [feature for feature in features if isinstance(feature, PocketFeature)]
    bosses = [feature for feature in features if isinstance(feature, BossFeature)]

    profile_loop = _normalize_profile_loop(base_feature.profile_loops[0])
    lines: list[str] = [
        "from build123d import BuildPart, BuildSketch, Plane, Polygon, Circle, Locations, Mode, CounterSinkHole, Sphere, extrude",
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
