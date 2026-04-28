from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from mesh2cad.domain.types import ToleranceConfig
from mesh2cad.pipeline.orchestrator import PipelineResult, run_pipeline


def process_mesh(
    *,
    input_path: str | Path,
    output_dir: str | Path | None = None,
    sample_count: int = 5_000,
    simplify_target_faces: int | None = None,
    build: bool = True,
    tolerances: ToleranceConfig | None = None,
    auto_tune_sampling: bool = True,
    align_surface_metrics: bool = True,
    icp_iterations: int = 10,
    icp_seed: int = 0,
    include_script: bool = True,
    icp_hybrid_hull_weight: float | None = None,
    repair_component_index: int | None = None,
) -> dict[str, Any]:
    """API-oriented entrypoint that returns a JSON-friendly response payload."""
    result = run_pipeline(
        path=input_path,
        output_dir=output_dir if build else None,
        sample_count=sample_count,
        simplify_target_faces=simplify_target_faces,
        tolerances=tolerances,
        auto_tune_sampling=auto_tune_sampling,
        align_surface_metrics=align_surface_metrics,
        icp_iterations=icp_iterations,
        icp_seed=icp_seed,
        icp_hybrid_hull_weight=icp_hybrid_hull_weight,
        repair_component_index=repair_component_index,
    )
    return pipeline_result_to_dict(result, include_script=include_script)


def pipeline_result_to_dict(
    result: PipelineResult,
    *,
    include_script: bool = True,
) -> dict[str, Any]:
    build_payload = None
    if result.build is not None:
        build_payload = {
            "build_success": result.build.build_success,
            "step_path": result.build.step_path,
            "warnings": list(result.build.warnings),
            "metadata": dict(result.build.metadata),
            "script": result.build.script if include_script else None,
        }

    detection_payload = asdict(result.detection_report)
    detection_payload["part_class"] = result.detection_report.part_class.value
    validation_payload = asdict(result.validation_report) if result.validation_report else None

    return {
        "source_path": result.source_path,
        "output_dir": result.output_dir,
        "detection_report": _json_safe(detection_payload),
        "validation_report": _json_safe(validation_payload),
        "build": _json_safe(build_payload),
        "warnings": _json_safe(list(result.warnings)),
        "feature_kinds": _json_safe(list(result.feature_kinds)),
        "primitive_kinds": _json_safe(list(result.primitive_kinds)),
        "reconstruction_plan": _json_safe(result.reconstruction_plan.to_dict()),
        "debug": _json_safe(dict(result.debug)),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value
