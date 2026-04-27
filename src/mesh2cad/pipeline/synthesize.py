from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mesh2cad.cad.build123d_builder import BuildResult, build_step_from_script
from mesh2cad.cad.script_generator import generate_script
from mesh2cad.domain.features import Feature


@dataclass(slots=True)
class SynthesisResult:
    script: str
    build_success: bool
    step_path: str | None
    warnings: list[str]
    metadata: dict[str, object]
    build_result: BuildResult | None = None


def synthesize_build123d_script(
    features: list[Feature],
    output_dir: str | Path | None = None,
) -> SynthesisResult:
    """Turn inferred features into a first-pass build123d script and optionally build it."""
    script = generate_script(features)
    warnings: list[str] = []
    build_success = False
    step_path: str | None = None

    if output_dir is None:
        warnings.append("Script generation completed, but execution/export was not requested.")
        build_result = None
    else:
        build_result = build_step_from_script(script, output_dir)
        build_success = build_result.success
        step_path = build_result.step_path
        warnings.extend(build_result.errors)

    return SynthesisResult(
        script=script,
        build_success=build_success,
        step_path=step_path,
        warnings=warnings,
        metadata={
            "feature_count": len(features),
            "requested_build": output_dir is not None,
            **(build_result.metadata if output_dir is not None and build_result is not None else {}),
        },
        build_result=build_result,
    )
