"""Constrain HTTP API ``input_path`` / ``output_dir`` to the state directory."""

from __future__ import annotations

import os
from pathlib import Path

from mesh2cad.ui.state import get_state_dir


def _relax_input_path_guard() -> bool:
    return os.environ.get("MESH2CAD_RELAX_INPUT_PATH_GUARD", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def enforce_paths_under_state_dir(
    *,
    input_path: Path | None,
    output_dir: Path | None,
) -> None:
    """Raise ``ValueError`` if a path is set and lies outside ``MESH2CAD_STATE_DIR``.

    Set ``MESH2CAD_RELAX_INPUT_PATH_GUARD=1`` for local development only (arbitrary
    filesystem paths; not recommended on shared or production hosts).
    """
    if _relax_input_path_guard():
        return
    state = get_state_dir().resolve()
    for label, raw in (("input_path", input_path), ("output_dir", output_dir)):
        if raw is None:
            continue
        resolved = raw.expanduser().resolve()
        if not resolved.is_relative_to(state):
            raise ValueError(
                f"{label} must be inside MESH2CAD_STATE_DIR ({state}); got {resolved}. "
                "Upload files via multipart, copy inputs under the state directory, or set "
                "MESH2CAD_RELAX_INPUT_PATH_GUARD=1 for development only."
            )
