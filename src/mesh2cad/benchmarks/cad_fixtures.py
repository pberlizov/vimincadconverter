"""Small deterministic build123d scripts used for benchmark inputs."""

from __future__ import annotations


def two_hole_plate_script(*, scale: float = 1.0) -> str:
    """Rectangular plate with two through-holes (same topology as smoke tests)."""
    width = 12.0 * scale
    height = 8.0 * scale
    hole_offset = 2.0 * scale
    hole_radius = 1.0 * scale
    depth = 3.0 * scale
    return "\n".join(
        [
            "from build123d import BuildPart, BuildSketch, Rectangle, Circle, Locations, Mode, extrude",
            "",
            "with BuildPart() as part:",
            "    with BuildSketch():",
            f"        Rectangle({width:.6f}, {height:.6f})",
            f"        for x_pos in ({-hole_offset:.6f}, {hole_offset:.6f}):",
            "            with Locations((x_pos, 0)):",
            f"                Circle({hole_radius:.6f}, mode=Mode.SUBTRACT)",
            f"    extrude(amount={depth:.6f})",
            "",
            "result = part.part",
        ]
    )
