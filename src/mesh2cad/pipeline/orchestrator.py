from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from mesh2cad.domain.plan import PlanStage, ReconstructionPlan, build_reconstruction_plan
from mesh2cad.domain.reports import DetectionReport, ValidationReport
from mesh2cad.domain.types import PartClass, ToleranceConfig
from mesh2cad.mesh.analysis import analyze_scene
from mesh2cad.mesh.cleanup import repair_mesh, simplify_mesh
from mesh2cad.mesh.geometry_input import (
    PointCloudData,
    build_sampled_cloud_from_points,
    load_geometry,
    point_cloud_to_meshdata,
)
from mesh2cad.mesh.io import MeshData
from mesh2cad.mesh.point_normals import estimate_point_normals_knn
from mesh2cad.mesh.sampling import SampledCloud, sample_surface
from mesh2cad.pipeline.fit_primitives import PrimitiveFitResult, fit_primitives
from mesh2cad.domain.features import BaseExtrudeFeature
from mesh2cad.pipeline.infer_features import FeatureInferenceResult, infer_features
from mesh2cad.pipeline.infer_revolve import infer_simple_revolve_solid
from mesh2cad.pipeline.perf import effective_sample_count, suggest_simplify_target_faces
from mesh2cad.pipeline.synthesize import SynthesisResult, synthesize_build123d_script
from mesh2cad.pipeline.validate import validate_reconstruction


@dataclass(slots=True)
class PipelineResult:
    source_path: str
    output_dir: str | None
    detection_report: DetectionReport
    validation_report: ValidationReport | None
    build: SynthesisResult | None
    warnings: list[str]
    feature_kinds: list[str]
    primitive_kinds: list[str]
    debug: dict[str, Any]
    reconstruction_plan: ReconstructionPlan


def run_pipeline(
    path: str | Path,
    output_dir: str | Path | None = None,
    *,
    sample_count: int = 5_000,
    simplify_target_faces: int | None = None,
    tolerances: ToleranceConfig | None = None,
    auto_tune_sampling: bool = True,
    align_surface_metrics: bool = True,
    icp_iterations: int = 10,
    icp_seed: int = 0,
) -> PipelineResult:
    """Run the supported mesh-to-CAD pipeline from file input to synthesis output."""
    tolerances = tolerances or ToleranceConfig()
    stages: list[PlanStage] = []

    geom = load_geometry(path)
    pc_with_normals: PointCloudData | None = None
    if isinstance(geom, PointCloudData):
        normals = (
            geom.normals
            if geom.normals is not None
            else estimate_point_normals_knn(np.asarray(geom.points, dtype=np.float64))
        )
        pc_with_normals = PointCloudData(
            points=np.asarray(geom.points, dtype=np.float64),
            normals=normals,
            source_path=geom.source_path,
        )
        loaded_mesh = point_cloud_to_meshdata(pc_with_normals)
        stages.append(
            PlanStage(
                "load_point_cloud",
                True,
                f"{len(pc_with_normals.points)} points → hull proxy mesh",
            )
        )
    elif isinstance(geom, MeshData):
        loaded_mesh = geom
        stages.append(PlanStage("load_mesh", True, f"Loaded {loaded_mesh.source_path.name}"))
    else:
        raise TypeError(f"Unsupported geometry input: {type(geom)!r}")

    repaired_mesh = repair_mesh(loaded_mesh)
    stages.append(PlanStage("repair_mesh", True, "Repair and largest-component selection"))

    working_mesh = repaired_mesh
    if simplify_target_faces is not None:
        working_mesh = simplify_mesh(repaired_mesh, simplify_target_faces)
        stages.append(PlanStage("simplify_mesh", True, f"Target faces ≤ {simplify_target_faces}"))
    else:
        stages.append(PlanStage("simplify_mesh", True, "No simplification requested"))

    n_samples = effective_sample_count(
        sample_count,
        face_count=int(len(working_mesh.faces)),
        vertex_count=int(len(working_mesh.vertices)),
        auto_tune=auto_tune_sampling,
    )
    simplify_hint = suggest_simplify_target_faces(int(len(loaded_mesh.faces)))

    if pc_with_normals is not None:
        cloud = build_sampled_cloud_from_points(pc_with_normals, count=n_samples)
    else:
        cloud = sample_surface(working_mesh, count=n_samples)
    stages.append(PlanStage("sample_surface", True, f"{len(cloud.points)} surface samples"))

    scene = analyze_scene(cloud)
    stages.append(
        PlanStage(
            "analyze_scene",
            True,
            f"Part class hint: {scene.part_class.value}",
        )
    )

    primitive_result = fit_primitives(cloud, tolerances)
    stages.append(
        PlanStage(
            "fit_primitives",
            bool(primitive_result.primitives),
            f"{len(primitive_result.primitives)} primitives",
        )
    )

    feature_result = infer_features(
        primitives=primitive_result.primitives,
        scene=scene,
        cloud=cloud,
        tolerances=tolerances,
    )
    stages.append(
        PlanStage(
            "infer_prismatic_features",
            any(isinstance(f, BaseExtrudeFeature) for f in feature_result.features),
            f"{len(feature_result.features)} features before rotational routing",
        )
    )

    if scene.part_class == PartClass.ROTATIONAL:
        revolve_result = infer_simple_revolve_solid(primitive_result.primitives, tolerances)
        if revolve_result.features:
            feature_result = FeatureInferenceResult(
                features=revolve_result.features,
                warnings=[*feature_result.warnings, *revolve_result.warnings],
            )
            stages.append(
                PlanStage(
                    "infer_revolve_override",
                    True,
                    "Rotational part class: using cylinder → revolve route",
                )
            )
        else:
            stages.append(
                PlanStage(
                    "infer_revolve_override",
                    False,
                    revolve_result.warnings[0] if revolve_result.warnings else "No revolve solid",
                )
            )

    build_result: SynthesisResult | None = None
    if feature_result.features:
        build_result = synthesize_build123d_script(feature_result.features, output_dir=output_dir)
        stages.append(PlanStage("synthesize_script", True, "build123d script generated"))
        if output_dir is not None:
            stages.append(
                PlanStage(
                    "build_export",
                    bool(build_result.build_success),
                    "STEP/STL export OK" if build_result and build_result.build_success else "Build/export skipped or failed",
                )
            )
        else:
            stages.append(PlanStage("build_export", True, "Build not requested (no output_dir)"))
    else:
        stages.append(PlanStage("synthesize_script", False, "No inferred features; nothing to build"))

    warnings = [*primitive_result.warnings, *feature_result.warnings]
    if build_result is not None:
        warnings.extend(build_result.warnings)

    validation_report = validate_reconstruction(
        working_mesh,
        build_result.build_result if build_result else None,
        align_surface_metrics=align_surface_metrics,
        icp_iterations=icp_iterations,
        icp_seed=icp_seed,
    )
    if validation_report is not None and validation_report.warnings:
        warnings.extend(validation_report.warnings)

    primitive_kinds = [primitive.kind.value for primitive in primitive_result.primitives]
    reconstruction_plan = build_reconstruction_plan(
        part_class=scene.part_class,
        features=feature_result.features,
        primitive_kinds=primitive_kinds,
        tolerances=tolerances,
        stages=stages,
    )

    return PipelineResult(
        source_path=str(loaded_mesh.source_path),
        output_dir=str(Path(output_dir).expanduser().resolve()) if output_dir is not None else None,
        detection_report=_build_detection_report(
            part_class=scene.part_class,
            primitive_result=primitive_result,
            feature_result=feature_result,
        ),
        validation_report=validation_report,
        build=build_result,
        warnings=warnings,
        feature_kinds=[feature.kind.value for feature in feature_result.features],
        primitive_kinds=primitive_kinds,
        debug=_debug_payload(
            loaded_mesh=loaded_mesh,
            working_mesh=working_mesh,
            cloud=cloud,
            primitive_result=primitive_result,
            feature_result=feature_result,
            sample_count=sample_count,
            effective_sample_count=n_samples,
            simplify_target_faces=simplify_target_faces,
            simplify_mesh_hint=simplify_hint,
            auto_tune_sampling=auto_tune_sampling,
        ),
        reconstruction_plan=reconstruction_plan,
    )


def _build_detection_report(
    *,
    part_class: PartClass,
    primitive_result: PrimitiveFitResult,
    feature_result: FeatureInferenceResult,
) -> DetectionReport:
    confidences = [feature.confidence.score for feature in feature_result.features]
    reconstruction_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return DetectionReport(
        part_class=part_class,
        warnings=[*primitive_result.warnings, *feature_result.warnings],
        detected_primitives=len(primitive_result.primitives),
        inferred_features=len(feature_result.features),
        reconstruction_confidence=reconstruction_confidence,
    )


def _debug_payload(
    *,
    loaded_mesh: MeshData,
    working_mesh: MeshData,
    cloud: SampledCloud,
    primitive_result: PrimitiveFitResult,
    feature_result: FeatureInferenceResult,
    sample_count: int,
    effective_sample_count: int,
    simplify_target_faces: int | None,
    simplify_mesh_hint: int | None,
    auto_tune_sampling: bool,
) -> dict[str, Any]:
    return {
        "input_faces": int(len(loaded_mesh.faces)),
        "working_faces": int(len(working_mesh.faces)),
        "sample_count": int(len(cloud.points)),
        "requested_sample_count": sample_count,
        "effective_sample_count": effective_sample_count,
        "auto_tune_sampling": auto_tune_sampling,
        "simplify_target_faces": simplify_target_faces,
        "simplify_mesh_face_hint": simplify_mesh_hint,
        "primitive_support_counts": [
            len(primitive.region.point_indices) for primitive in primitive_result.primitives
        ],
        "feature_parameters": [asdict(feature) for feature in feature_result.features],
    }
