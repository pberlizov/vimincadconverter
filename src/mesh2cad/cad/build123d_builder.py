from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

from mesh2cad.security.cad_script_runtime import cad_script_safe_builtins


@dataclass(slots=True)
class BuildResult:
    success: bool
    step_path: str | None
    errors: list[str]
    metadata: dict[str, Any]


def build_step_from_script(script: str, output_dir: str | Path) -> BuildResult:
    """Execute a generated build123d script and export a STEP file when possible."""
    runtime = _load_build123d_runtime()
    if runtime is None:
        return BuildResult(
            success=False,
            step_path=None,
            errors=["build123d is not installed; cannot execute generated CAD script."],
            metadata={},
        )

    try:
        result_object = _execute_script(script, runtime["globals"])
    except Exception as exc:  # pragma: no cover - exercised through tests with controlled errors
        return BuildResult(
            success=False,
            step_path=None,
            errors=[f"Generated script execution failed: {exc}"],
            metadata={},
        )

    try:
        output_path = Path(output_dir).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        step_path = output_path / "model.step"
        runtime["export_step"](result_object, step_path)
        preview_path = output_path / "model_preview.stl"
        runtime["export_stl"](result_object, preview_path)
    except Exception as exc:  # pragma: no cover - exercised through tests with controlled errors
        return BuildResult(
            success=False,
            step_path=None,
            errors=[f"STEP export failed: {exc}"],
            metadata={},
        )

    return BuildResult(
        success=True,
        step_path=str(step_path),
        errors=[],
        metadata=_result_metadata(result_object, preview_path=preview_path),
    )


def _load_build123d_runtime() -> dict[str, Any] | None:
    if importlib.util.find_spec("build123d") is None:
        return None

    build123d_module = import_module("build123d")
    export_step = getattr(build123d_module, "export_step", None)
    export_stl = getattr(build123d_module, "export_stl", None)
    if export_step is None:
        exporters_module = import_module("build123d.exporters")
        export_step = getattr(exporters_module, "export_step", None)
        if export_stl is None:
            export_stl = getattr(exporters_module, "export_stl", None)
    if export_step is None:
        raise AttributeError("No compatible build123d export_step function is available.")
    if export_stl is None:
        raise AttributeError("No compatible build123d export_stl function is available.")

    runtime_globals = dict(cad_script_safe_builtins())
    runtime_globals.update(_public_module_symbols(build123d_module))
    return {
        "globals": runtime_globals,
        "export_step": export_step,
        "export_stl": export_stl,
    }


def _execute_script(script: str, runtime_globals: dict[str, Any]) -> Any:
    execution_globals = dict(runtime_globals)
    exec(script, execution_globals, execution_globals)
    if "result" not in execution_globals:
        raise ValueError("Generated script did not define a 'result' object.")
    return execution_globals["result"]


def _public_module_symbols(module: ModuleType) -> dict[str, Any]:
    exported: dict[str, Any] = {}
    for name in dir(module):
        if name.startswith("_"):
            continue
        exported[name] = getattr(module, name)
    return exported


def _result_metadata(result_object: Any, *, preview_path: Path | None = None) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    volume = getattr(result_object, "volume", None)
    if volume is not None:
        metadata["volume"] = float(volume)
    is_valid = getattr(result_object, "is_valid", None)
    if is_valid is not None:
        metadata["solid_valid"] = bool(is_valid)
    is_manifold = getattr(result_object, "is_manifold", None)
    if is_manifold is not None:
        metadata["solid_manifold"] = bool(is_manifold)

    bounding_box = getattr(result_object, "bounding_box", None)
    if callable(bounding_box):
        bbox = bounding_box()
        size = getattr(bbox, "size", None)
        if size is not None:
            metadata["bbox_extents"] = [float(size.X), float(size.Y), float(size.Z)]
    if preview_path is not None:
        metadata["preview_stl_path"] = str(preview_path)
    return metadata
