from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def export_step(part: Any, path: str | Path, export_step_func: Callable[[Any, str | Path], None]) -> None:
    """Thin wrapper around a concrete STEP exporter."""
    output_path = Path(path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export_step_func(part, output_path)
