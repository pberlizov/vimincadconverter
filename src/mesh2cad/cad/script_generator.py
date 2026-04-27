from __future__ import annotations

from mesh2cad.domain.features import BaseExtrudeFeature, Feature, RevolveSolidFeature, ThroughHoleFeature
from mesh2cad.cad.vector_utils import (
    format_tuple3,
    revolve_sketch_frame,
    sketch_plane_vectors,
)


def generate_script(features: list[Feature]) -> str:
    """Generate a narrow build123d script for the currently supported feature set."""
    revolve_feature = next((feature for feature in features if isinstance(feature, RevolveSolidFeature)), None)
    base_feature = next(
        (feature for feature in features if isinstance(feature, BaseExtrudeFeature)),
        None,
    )

    if revolve_feature is not None and base_feature is None:
        return _generate_revolve_script(revolve_feature)

    if base_feature is None:
        raise ValueError("A BaseExtrudeFeature or RevolveSolidFeature is required to generate a CAD script.")

    through_holes = [
        feature for feature in features if isinstance(feature, ThroughHoleFeature)
    ]

    profile_loop = _normalize_profile_loop(base_feature.profile_loops[0])
    lines: list[str] = [
        "from build123d import BuildPart, BuildSketch, Plane, Polygon, Circle, Locations, Mode, extrude",
        "",
        f"DEPTH = {base_feature.depth:.6f}",
        "PROFILE = [",
    ]

    for x_coord, y_coord in profile_loop:
        lines.append(f"    ({x_coord:.6f}, {y_coord:.6f}),")
    lines.append("]")

    if through_holes:
        lines.append("HOLES = [")
        for hole in through_holes:
            lines.append(
                f"    ({hole.center_xy[0]:.6f}, {hole.center_xy[1]:.6f}, {hole.radius:.6f}),"
            )
        lines.append("]")
    else:
        lines.append("HOLES = []")

    sketch_block = _extrude_sketch_block(base_feature)
    lines.extend(sketch_block)

    return "\n".join(lines)


def _extrude_sketch_block(base_feature: BaseExtrudeFeature) -> list[str]:
    sp = base_feature.sketch_plane
    if isinstance(sp, dict) and all(k in sp for k in ("origin", "x_dir", "z_dir")):
        origin, x_dir, z_dir = sketch_plane_vectors(sp)
        return [
            "",
            f"ORIGIN = {format_tuple3(origin)}",
            f"X_DIR = {format_tuple3(x_dir)}",
            f"Z_DIR = {format_tuple3(z_dir)}",
            "SKETCH_PLANE = Plane(origin=ORIGIN, x_dir=X_DIR, z_dir=Z_DIR)",
            "",
            "with BuildPart() as part:",
            "    with BuildSketch(SKETCH_PLANE) as profile:",
            "        Polygon(*PROFILE)",
            "        for x_pos, y_pos, radius in HOLES:",
            "            with Locations((x_pos, y_pos)):",
            "                Circle(radius, mode=Mode.SUBTRACT)",
            "    extrude(amount=DEPTH)",
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
