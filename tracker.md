# ViminCADConverter Tracker

This document tracks what we intend to build, how we will verify it, and what is physically present in the repository.

Legend:
- `[x]` implemented and verified in the repo
- `[~]` partially implemented or implemented but not yet strongly verified
- `[ ]` not implemented yet

## Audit Rule

- [x] Every coding step ends with an audit of what files, behaviors, and tests are physically present.
- [x] Every completed item should reference a concrete verification method.
- [x] We prefer "verified by test or command" over "I think this exists."

## Repository Foundation

- [x] `pyproject.toml` exists.
  Verification:
  - Open the file and confirm package metadata, dependencies, and editable package layout.
- [x] `README.md` exists.
  Verification:
  - Open the file and confirm the project is described as Mesh2CAD.
- [x] `src/mesh2cad/__init__.py` exists.
  Verification:
  - Confirm the package imports successfully after editable install.
- [x] `src/mesh2cad/main.py` exists.
  Verification:
  - Run `python -m mesh2cad.main` or inspect the file.
- [x] Editable install works.
  Verification:
  - Run `python3 -m pip install -e '.[dev]'`.
- [x] `pytest` is configured.
  Verification:
  - Run `pytest -q`.

## Domain Model Objectives

- [x] Part classification enum exists.
  Verification:
  - Inspect `src/mesh2cad/domain/types.py`.
- [x] Primitive kind enum exists.
  Verification:
  - Inspect `src/mesh2cad/domain/types.py`.
- [x] Feature kind enum exists.
  Verification:
  - Inspect `src/mesh2cad/domain/types.py`.
- [x] Confidence dataclass exists.
  Verification:
  - Inspect `src/mesh2cad/domain/types.py`.
- [x] Tolerance configuration dataclass exists.
  Verification:
  - Inspect `src/mesh2cad/domain/types.py`.
- [x] Axis3D dataclass exists.
  Verification:
  - Inspect `src/mesh2cad/domain/geometry.py`.
- [x] Frame3D dataclass exists.
  Verification:
  - Inspect `src/mesh2cad/domain/geometry.py`.
- [x] BoundingBox dataclass exists.
  Verification:
  - Inspect `src/mesh2cad/domain/geometry.py`.
- [x] PrimitiveRegion dataclass exists.
  Verification:
  - Inspect `src/mesh2cad/domain/primitives.py`.
- [x] Base Primitive dataclass exists.
  Verification:
  - Inspect `src/mesh2cad/domain/primitives.py`.
- [x] PlanePrimitive dataclass exists.
  Verification:
  - Inspect `src/mesh2cad/domain/primitives.py`.
- [x] CylinderPrimitive dataclass exists.
  Verification:
  - Inspect `src/mesh2cad/domain/primitives.py`.
- [x] Base Feature dataclass exists.
  Verification:
  - Inspect `src/mesh2cad/domain/features.py`.
- [x] BaseExtrudeFeature dataclass exists.
  Verification:
  - Inspect `src/mesh2cad/domain/features.py`.
- [x] ThroughHoleFeature dataclass exists.
  Verification:
  - Inspect `src/mesh2cad/domain/features.py`.
- [x] DetectionReport dataclass exists.
  Verification:
  - Inspect `src/mesh2cad/domain/reports.py`.
- [x] ValidationReport dataclass exists.
  Verification:
  - Inspect `src/mesh2cad/domain/reports.py`.

## Mesh Input Objectives

- [x] Mesh loading module exists.
  Verification:
  - Inspect `src/mesh2cad/mesh/io.py`.
- [x] MeshData dataclass exists.
  Verification:
  - Inspect `src/mesh2cad/mesh/io.py`.
- [x] Mesh loader supports path strings and `Path`.
  Verification:
  - Inspect type hints and code in `load_mesh`.
- [x] Mesh loader normalizes output to a single `trimesh.Trimesh`.
  Verification:
  - Inspect `load_mesh`.
- [x] Mesh loader rejects empty meshes.
  Verification:
  - Inspect `load_mesh` guard clauses.
- [x] Mesh loader captures vertex normals when available.
  Verification:
  - Inspect `load_mesh`.
- [x] Mesh loader stores source path.
  Verification:
  - Inspect `MeshData`.

## Mesh Cleanup Objectives

- [x] Cleanup module exists.
  Verification:
  - Inspect `src/mesh2cad/mesh/cleanup.py`.
- [x] Conservative repair function exists.
  Verification:
  - Inspect `repair_mesh`.
- [x] Repair removes unreferenced vertices.
  Verification:
  - Inspect `repair_mesh`.
- [x] Repair filters degenerate faces using current trimesh API.
  Verification:
  - Inspect `mesh.nondegenerate_faces()` use in `repair_mesh`.
- [x] Repair filters duplicate faces using current trimesh API.
  Verification:
  - Inspect `mesh.unique_faces()` use in `repair_mesh`.
- [x] Repair handles multibody meshes by keeping largest component.
  Verification:
  - Inspect `repair_mesh`.
- [x] Repair fixes normals and inversion.
  Verification:
  - Inspect `repair_mesh`.
- [x] Simplification function exists.
  Verification:
  - Inspect `simplify_mesh`.
- [x] Simplification has input validation.
  Verification:
  - Inspect `simplify_mesh`.

## Mesh Sampling Objectives

- [x] Sampling module exists.
  Verification:
  - Inspect `src/mesh2cad/mesh/sampling.py`.
- [x] SampledCloud dataclass exists.
  Verification:
  - Inspect `SampledCloud`.
- [x] Surface sampling function exists.
  Verification:
  - Inspect `sample_surface`.
- [x] Sampling returns points.
  Verification:
  - Verified by test.
- [x] Sampling returns face-derived normals when available.
  Verification:
  - Inspect `sample_surface`.
- [x] Sampling returns source face indices.
  Verification:
  - Inspect `sample_surface`.

## Scene Analysis Objectives

- [x] Analysis module exists.
  Verification:
  - Inspect `src/mesh2cad/mesh/analysis.py`.
- [x] SceneAnalysis dataclass exists.
  Verification:
  - Inspect `SceneAnalysis`.
- [x] PCA-based principal axes estimation exists.
  Verification:
  - Inspect `analyze_scene`.
- [x] Dominant normal extraction exists.
  Verification:
  - Inspect `analyze_scene`.
- [x] Coarse symmetry plane generation exists.
  Verification:
  - Inspect `analyze_scene`.
- [x] Coarse part classification exists.
  Verification:
  - Inspect `analyze_scene`.

## Primitive Fitting Objectives

- [x] Primitive fitting module exists.
  Verification:
  - Inspect `src/mesh2cad/pipeline/fit_primitives.py`.
- [x] PrimitiveFitResult dataclass exists.
  Verification:
  - Inspect `PrimitiveFitResult`.
- [x] `fit_primitives` entrypoint exists.
  Verification:
  - Inspect `fit_primitives`.
- [x] Plane candidate extraction from normals exists.
  Verification:
  - Inspect helper functions in `fit_primitives.py`.
- [x] Points are grouped by approximate coplanarity along candidate normals.
  Verification:
  - Inspect distance-based clustering logic in `fit_primitives.py`.
- [x] Plane primitives can be emitted from sampled point clouds.
  Verification:
  - Verified by test on a box mesh.
- [x] Leftover point indices are returned.
  Verification:
  - Inspect `fit_primitives` return value and verify via test.
- [x] Cylinder primitive fitting exists.
  Verification:
  - Verified by test on a synthetic cylinder mesh.
- [x] Multiple cylinder primitive fitting exists.
  Verification:
  - Verified by synthetic multi-cylinder sampled-cloud test.
- [x] Cone primitive fitting exists.
  Verification:
  - Verified by synthetic cone mesh primitive-fitting test in both interpreters.
- [x] Sphere primitive fitting exists.
  Verification:
  - Verified by synthetic sphere mesh primitive-fitting test in both interpreters.

## Feature Inference Objectives

- [x] Feature inference module exists.
  Verification:
  - Inspect `src/mesh2cad/pipeline/infer_features.py` and run `pytest -q`.
- [x] Base extrusion inference exists.
  Verification:
  - Verified by synthetic plane-pair test.
- [x] Polygonal base profile synthesis exists.
  Verification:
  - Verified by convex-profile inference and script-generation tests.
- [x] Through-hole inference exists.
  Verification:
  - Verified by synthetic plate-with-hole feature test.
- [x] Countersink inference exists.
  Verification:
  - Verified by cone-and-cylinder feature-inference tests and generated script coverage.
- [x] Blind-hole inference exists.
  Verification:
  - Verified by synthetic blind-hole feature tests, including angled-axis coverage.
- [x] Boss inference exists.
  Verification:
  - Verified by synthetic protrusion feature-inference test and boss script-generation test.
- [x] Pocket inference exists.
  Verification:
  - Verified by synthetic planar-pocket feature-inference test and build-enabled pocket script test.
- [x] Spherical boss inference exists.
  Verification:
  - Verified by synthetic sphere-backed protrusion inference test and generated script coverage.
- [x] Spherical cavity inference exists.
  Verification:
  - Verified by synthetic sphere-backed cavity inference test and generated script coverage.
- [x] Simple revolve inference exists.
  Verification:
  - Verified by revolve inference tests and generated revolve script coverage.

## CAD Synthesis Objectives

- [x] CAD package directory exists.
  Verification:
  - Inspect `src/mesh2cad/cad/` and run `pytest -q`.
- [x] Script generator exists.
  Verification:
  - Verified by tests that inspect generated code content.
- [x] Build123d builder exists.
  Verification:
  - Verified by tests for missing-dependency handling and synthesis integration.
- [x] STEP export exists.
  Verification:
  - Verified by Python 3.11 tests that write a non-empty `model.step`.
- [x] Reconstruction metadata report exists.
  Verification:
  - Verified in synthesis wrapper test metadata assertions.
- [x] Preview STL export exists.
  Verification:
  - Verified by Python 3.11 build-enabled tests that write a non-empty preview STL.
- [x] Countersink CAD synthesis exists.
  Verification:
  - Verified by generated script assertions and build-enabled countersink tests.
- [x] Blind-hole CAD synthesis exists.
  Verification:
  - Verified by generated script assertions and build-enabled blind-hole tests.
- [x] Pocket CAD synthesis exists.
  Verification:
  - Verified by generated script assertions and build-enabled pocket tests.
- [x] Boss CAD synthesis exists.
  Verification:
  - Verified by generated script assertions and build-enabled boss tests.
- [x] Spherical boss/cavity CAD synthesis exists.
  Verification:
  - Verified by generated script assertions for additive and subtractive sphere operations.
- [x] Revolve CAD synthesis exists.
  Verification:
  - Verified by revolve script-generation tests.

## Orchestration Objectives

- [x] Pipeline orchestrator module exists.
  Verification:
  - Inspect `src/mesh2cad/pipeline/orchestrator.py` and run `pytest -q`.
- [x] End-to-end pipeline result object exists.
  Verification:
  - Verified by orchestrator tests.
- [x] Python-callable API service exists.
  Verification:
  - Inspect `src/mesh2cad/api/service.py` and run `pytest -q`.
- [x] CLI calls the API service.
  Verification:
  - Verified by CLI JSON-output test.
- [x] Optional HTTP app factory exists.
  Verification:
  - Inspect `src/mesh2cad/api/app.py`.
- [x] HTTP request/response path is tested.
  Verification:
  - Verified by FastAPI `TestClient` endpoint test under Python 3.11.
- [x] Background job runner exists.
  Verification:
  - Inspect `src/mesh2cad/jobs/runner.py` and run async job tests.
- [x] Async job status endpoints exist.
  Verification:
  - Verified by UI/API polling tests.
- [x] Async job cancellation exists.
  Verification:
  - Verified by HTTP cancel endpoint tests and runner cancel-marker behavior.
- [x] Async job retry exists.
  Verification:
  - Verified by HTTP and UI retry-after-completion tests.

## UI Objectives

- [x] API package exists.
  Verification:
  - Inspect `src/mesh2cad/api/` and run `pytest -q`.
- [x] Authenticated web UI exists.
  Verification:
  - Inspect `src/mesh2cad/ui/` and run UI tests.
- [x] Initial admin bootstrap flow exists.
  Verification:
  - Verified by UI setup test.
- [x] Session-based login and logout exist.
  Verification:
  - Verified by UI setup/login flow test.
- [x] Upload/process dashboard exists.
  Verification:
  - Verified by dashboard and job-creation test.
- [x] Job detail page exists.
  Verification:
  - Verified by UI detail-page test.
- [x] Export controls exist.
  Verification:
  - Verified by report/script download tests.
- [x] Side-by-side geometry preview exists.
  Verification:
  - Verified by job-detail UI test and preview artifact availability.
- [x] Retry controls exist.
  Verification:
  - Verified by UI retry route test and job detail template wiring.

## Validation Objectives

- [x] Validation module exists.
  Verification:
  - Inspect `src/mesh2cad/pipeline/validate.py` and run `pytest -q`.
- [x] RMS error measurement exists.
  Verification:
  - Verified as first-pass bbox extents delta ratio in tests.
- [x] Max error measurement exists.
  Verification:
  - Verified as first-pass bbox extents delta ratio in tests.
- [x] Volume delta measurement exists.
  Verification:
  - Verified by synthetic solid comparison tests.
- [x] Invalid solid warnings exist.
  Verification:
  - Verified by direct validation test with invalid/non-manifold CAD metadata.

## Test Corpus Objectives

- [x] At least one smoke test exists.
  Verification:
  - Run `pytest -q`.
- [x] Synthetic box fixture is created in tests.
  Verification:
  - Inspect `tests/test_mesh_pipeline_smoke.py`.
- [x] Load/repair/sample/analyze path is tested.
  Verification:
  - Run `pytest -q`.
- [x] Primitive fitting on a simple box is tested.
  Verification:
  - Run `pytest -q` after the primitive-fitting test lands.
- [x] Plate-with-holes synthetic fixture exists.
  Verification:
  - Inspect `tests/test_mesh_pipeline_smoke.py` and run `pytest -q`.
- [x] L-bracket fixture exists.
  Verification:
  - Verified by mesh-backed L-bracket pipeline test.
- [x] Cylindrical spacer fixture exists.
  Verification:
  - Inspect `tests/test_mesh_pipeline_smoke.py` and run `pytest -q`.
- [x] Noisy mesh variants exist.
  Verification:
  - Inspect `tests/test_mesh_pipeline_smoke.py` artifact and scan-like regressions and run `pytest -q`.

## Documentation Objectives

- [x] High-level README exists.
  Verification:
  - Open `README.md`.
- [x] Tracker exists.
  Verification:
  - Open `tracker.md`.
- [x] Architecture doc exists.
  Verification:
  - Open `docs/architecture.md`.
- [x] MVP definition doc exists.
  Verification:
  - Open `docs/mvp.md`.
- [x] Supported geometry classes doc exists.
  Verification:
  - Open `docs/supported-parts.md`.
- [x] Failure modes doc exists.
  Verification:
  - Open `docs/failure-modes.md`.

## Process Objectives

- [x] End-of-step audit discipline is adopted.
  Verification:
  - Check assistant close-out notes for "physically present" audit.
- [x] Tests are run after code changes so far.
  Verification:
  - `pytest -q` passed after initial scaffold and repair fix.
- [~] The tracker is updated as implementation advances.
  Verification:
  - Re-open and compare against repo state after each coding step.
- [ ] Branching workflow exists.
  Verification:
  - Initialize git and inspect branch name.
- [x] CI exists.
  Verification:
  - Inspect `.github/workflows/ci.yml` and verify it runs `pytest` in matrix jobs.

## Near-Term Build Queue

- [x] Create project scaffold.
  Verification:
  - Files exist in `src/mesh2cad/`.
- [x] Make mesh ingestion work.
  Verification:
  - Smoke test passes.
- [x] Make mesh repair work.
  Verification:
  - Smoke test passes.
- [x] Make sampling work.
  Verification:
  - Smoke test passes.
- [x] Make coarse scene analysis work.
  Verification:
  - Smoke test passes.
- [x] Replace primitive-fitting stub with first plane-detection pass.
  Verification:
  - Run primitive-fitting tests on a synthetic box.
- [x] Add first cylinder-detection pass.
  Verification:
  - Run cylinder fixture tests with `pytest -q`.
- [x] Add feature inference for base extrudes.
  Verification:
  - Verified by synthetic plane-pair and bracket reconstruction tests.
- [x] Add script synthesis.
  Verification:
  - Verified by generated code content tests and synthesis wrapper tests.
- [x] Add STEP export.
  Verification:
  - Verified by Python 3.11 tests that write a non-empty `model.step`.

## Breadth Expansion Queue

These are the next broadening moves that increase the product's addressable mechanical surface area rather than only polishing existing single-feature routes.

- [x] Hole-stack abstraction exists.
  Verification:
  - Inspect the feature/domain model for a structured axial hole representation.
  - Verify by tests that represent at least two stacked-section hole cases with one shared axis.
- [x] Counterbore inference exists.
  Verification:
  - Add feature-inference tests for coaxial stepped cylindrical bores from one entry face.
  - Verify generated CAD script output includes the stepped-bore reconstruction.
- [x] Tapered blind-hole inference exists.
  Verification:
  - Add cone-plus-cylinder feature tests that emit a tapered blind-hole or equivalent structured hole stack.
- [x] Tapered boss inference exists.
  Verification:
  - Add cone-backed protrusion tests and verify generated additive CAD output.
- [~] Multi-face prismatic reconstruction exists (secondary stock inference + benchmark).
  Verification:
  - Benchmark `side_tab_plate_multiface_prismatic` in `benchmarks/cases.json` expects two `base_extrude` features and the multi-base synthesis warning.
  - Generated build123d script still serializes the **primary** stock first; full dual-stock CAD export is tracked separately.
- [ ] Multi-stock / additive prismatic sequencing exists.
  Verification:
  - Add tests for an L-bracket-like or gusseted part that requires more than one additive stock feature.
- [ ] Counterbore plus countersink coexistence on one axis is supported.
  Verification:
  - Add a structured hole-stack test with multiple entry modifiers on one shared axis.
- [x] Point-cloud-native benchmark cases exist.
  Verification:
  - Benchmark `point_cloud_cylinder_revolve` (and existing `box_point_cloud_*` cases) use `.xyz` inputs only.
  - Run `pytest tests/test_benchmarks.py -k point_cloud_cylinder`.
- [x] Multi-body selection or splitting exists (component index).
  Verification:
  - `repair_mesh(..., component_index=…)` and `run_pipeline(..., repair_component_index=…)` plus CLI `--repair-component-index`.
  - Tests in `tests/test_repair_multibody.py` and catalog case `multibody_second_component_box`.
- [ ] Rotational route supports tapered profiles from cone primitives.
  Verification:
  - Add tests that infer a tapered revolve-capable profile from cone-dominant rotational input.
- [~] Real-part fixture pack exists (v1 starter).
  Verification:
  - Directory `benchmarks/fixtures/` with `README.md`, committed `noisy_plate.stl`, and catalog case `fixture_noisy_plate_prismatic`.
  - Expand the pack over time with additional small scan-like meshes or clouds.

## End-of-Step Physical Audit Template

- Files added this step:
  - Fill in exact paths.
- Files modified this step:
  - Fill in exact paths.
- Commands run this step:
  - Fill in exact commands.
- Tests passed this step:
  - Fill in exact test names or commands.
- Behaviors now physically present:
  - Fill in concrete, observable capabilities.
- Gaps still not physically present:
  - Fill in what remains absent.

## Step Audit 2026-04-26 A

- Files added this step:
  - `tracker.md`
- Files modified this step:
  - `src/mesh2cad/pipeline/fit_primitives.py`
  - `tests/test_mesh_pipeline_smoke.py`
- Commands run this step:
  - `find . -maxdepth 3 -type f | sort`
  - `sed -n '1,220p' src/mesh2cad/pipeline/fit_primitives.py`
  - `sed -n '1,220p' tests/test_mesh_pipeline_smoke.py`
  - `pytest -q`
  - `sed -n '1,260p' tracker.md`
- Tests passed this step:
  - `tests/test_mesh_pipeline_smoke.py::test_mesh_load_repair_sample_analyze_smoke`
  - `tests/test_mesh_pipeline_smoke.py::test_fit_primitives_detects_box_planes`
  - Aggregate command: `pytest -q`
- Behaviors now physically present:
  - The repository contains a persistent tracker of objectives and verification methods.
  - The primitive fitting stage is no longer a pure stub.
  - `fit_primitives` can consume a sampled cloud with normals and emit detected plane primitives.
  - Plane hypotheses are grouped by approximate normal orientation.
  - Candidate planar slices are grouped by distance along each normal direction.
  - Plane primitives include origin, normal, support-point indices, projected area, and confidence.
  - Duplicate plane hypotheses are filtered using angular and offset tolerances.
  - Leftover point indices are returned for points not assigned to accepted planes.
  - The test suite now verifies plane detection on a synthetic box mesh.
  - The primitive fitting layer explicitly warns that cylinder fitting is not implemented yet.
- Gaps still not physically present:
  - Cylinder fitting is absent.
  - Feature inference is absent.
  - CAD synthesis is absent.
  - STEP export is absent.
  - UI is absent.
  - Validation metrics are absent.

## Step Audit 2026-04-26 B

- Files added this step:
  - None.
- Files modified this step:
  - `src/mesh2cad/pipeline/fit_primitives.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,320p' src/mesh2cad/pipeline/fit_primitives.py`
  - `sed -n '1,260p' tests/test_mesh_pipeline_smoke.py`
  - `sed -n '1,360p' tracker.md`
  - `pytest -q`
  - `python3 - <<'PY' ... PY` debug probe for cylinder primitive output
  - `pytest -q`
- Tests passed this step:
  - `tests/test_mesh_pipeline_smoke.py::test_mesh_load_repair_sample_analyze_smoke`
  - `tests/test_mesh_pipeline_smoke.py::test_fit_primitives_detects_box_planes`
  - `tests/test_mesh_pipeline_smoke.py::test_fit_primitives_detects_cylinder`
  - Aggregate command: `pytest -q`
- Behaviors now physically present:
  - The primitive fitter can emit `CylinderPrimitive` results.
  - Cylinder axis estimation now uses normal covariance over the sampled cloud.
  - Cylinder sidewall support is selected by low normal-axis alignment rather than by leftover points alone.
  - Cylinder primitives now include radius, axis direction, axis origin, estimated height, support region, area estimate, and confidence.
  - The test suite now verifies cylinder detection on a synthetic cylinder mesh with radius and height assertions.
  - The box-plane test still passes after adding cylinder detection, which gives us a basic regression check against obvious false positives.
- Gaps still not physically present:
  - Plane fitting still over-detects tessellated cylindrical side patches as planes in some cases.
  - Feature inference is absent.
  - CAD synthesis is absent.
  - STEP export is absent.
  - UI is absent.
  - Validation metrics are absent.

## Step Audit 2026-04-26 C

- Files added this step:
  - `src/mesh2cad/pipeline/infer_features.py`
- Files modified this step:
  - `src/mesh2cad/domain/features.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,260p' src/mesh2cad/domain/features.py`
  - `sed -n '1,260p' src/mesh2cad/mesh/analysis.py`
  - `sed -n '1,360p' src/mesh2cad/pipeline/fit_primitives.py`
  - `sed -n '1,260p' src/mesh2cad/domain/primitives.py`
  - `pytest -q`
  - `pytest -q`
- Tests passed this step:
  - `tests/test_mesh_pipeline_smoke.py::test_mesh_load_repair_sample_analyze_smoke`
  - `tests/test_mesh_pipeline_smoke.py::test_fit_primitives_detects_box_planes`
  - `tests/test_mesh_pipeline_smoke.py::test_fit_primitives_detects_cylinder`
  - `tests/test_mesh_pipeline_smoke.py::test_infer_features_detects_base_extrude_and_through_hole`
  - Aggregate command: `pytest -q`
- Behaviors now physically present:
  - The repository now has a feature inference module.
  - A base extrusion can be inferred from a dominant pair of parallel planes.
  - Base extrusion inference computes a sketch plane basis and a rectangular profile loop from projected support points.
  - Through holes can be inferred from cylinders aligned to the inferred extrusion axis.
  - Through-hole inference computes sketch-space center coordinates and carries radius/depth data.
  - The feature layer is now instantiable in tests after fixing dataclass field defaults.
  - The test suite now verifies one concrete CAD-like inference result: base extrude plus through-hole.
- Gaps still not physically present:
  - Feature inference is still narrow and rectangle-biased.
  - It does not infer multiple holes, pockets, bosses, or arbitrary outer profiles yet.
  - CAD synthesis is absent.
  - STEP export is absent.
  - UI is absent.
  - Validation metrics are absent.

## Step Audit 2026-04-26 D

- Files added this step:
  - `src/mesh2cad/cad/__init__.py`
  - `src/mesh2cad/cad/script_generator.py`
  - `src/mesh2cad/pipeline/synthesize.py`
- Files modified this step:
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,260p' src/mesh2cad/pipeline/infer_features.py`
  - `sed -n '1,220p' src/mesh2cad/domain/features.py`
  - `sed -n '1,320p' tracker.md`
  - `find src/mesh2cad -maxdepth 3 -type f | sort`
  - `pytest -q`
- Tests passed this step:
  - `tests/test_mesh_pipeline_smoke.py::test_mesh_load_repair_sample_analyze_smoke`
  - `tests/test_mesh_pipeline_smoke.py::test_fit_primitives_detects_box_planes`
  - `tests/test_mesh_pipeline_smoke.py::test_fit_primitives_detects_cylinder`
  - `tests/test_mesh_pipeline_smoke.py::test_infer_features_detects_base_extrude_and_through_hole`
  - `tests/test_mesh_pipeline_smoke.py::test_generate_build123d_script_from_features`
  - `tests/test_mesh_pipeline_smoke.py::test_synthesize_build123d_script_wraps_generated_code`
  - Aggregate command: `pytest -q`
- Behaviors now physically present:
  - The repository now has a CAD package.
  - The system can generate a first-pass `build123d` Python script from inferred `base_extrude + through_hole` features.
  - The generated script includes base dimensions, hole definitions, a rectangular sketch, subtractive circles, and an extrusion call.
  - There is now a synthesis wrapper that returns generated script text plus metadata and warnings.
  - The test suite verifies script content and synthesis metadata.
- Gaps still not physically present:
  - The generated script is not executed automatically.
  - There is no build123d runner yet.
  - There is no STEP export yet.
  - The current script generator only supports rectangular base extrudes and through-holes.
  - UI is absent.
  - Validation metrics are absent.

## Step Audit 2026-04-26 E

- Files added this step:
  - `src/mesh2cad/cad/build123d_builder.py`
  - `src/mesh2cad/cad/export.py`
- Files modified this step:
  - `src/mesh2cad/pipeline/synthesize.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,260p' src/mesh2cad/cad/script_generator.py`
  - `sed -n '1,260p' src/mesh2cad/pipeline/synthesize.py`
  - `sed -n '1,360p' tests/test_mesh_pipeline_smoke.py`
  - `python3 - <<'PY' ... PY`
  - `pytest -q`
  - `pytest -q`
- Tests passed this step:
  - `tests/test_mesh_pipeline_smoke.py::test_mesh_load_repair_sample_analyze_smoke`
  - `tests/test_mesh_pipeline_smoke.py::test_fit_primitives_detects_box_planes`
  - `tests/test_mesh_pipeline_smoke.py::test_fit_primitives_detects_cylinder`
  - `tests/test_mesh_pipeline_smoke.py::test_infer_features_detects_base_extrude_and_through_hole`
  - `tests/test_mesh_pipeline_smoke.py::test_generate_build123d_script_from_features`
  - `tests/test_mesh_pipeline_smoke.py::test_synthesize_build123d_script_wraps_generated_code`
  - `tests/test_mesh_pipeline_smoke.py::test_build_step_from_script_reports_missing_build123d`
  - `tests/test_mesh_pipeline_smoke.py::test_synthesize_build123d_script_reports_missing_build123d_when_requested`
  - Aggregate command: `pytest -q`
- Behaviors now physically present:
  - The repository now has a build runner for generated build123d scripts.
  - The build runner can detect whether `build123d` is installed before attempting execution.
  - The build runner can execute generated script text and look for a `result` object when runtime support is available.
  - The build runner can attempt STEP export to `model.step` inside a requested output directory when runtime support is available.
  - The synthesis wrapper can now optionally request a build/export attempt via `output_dir`.
  - Missing dependency behavior is tested and reported as warnings/errors instead of crashing.
- Gaps still not physically present:
  - `build123d` is not installed in the current environment, so successful execution/export has not been verified here yet.
  - A real non-empty STEP file has not been produced in this environment.
  - The current script generator still only supports rectangular base extrudes and through-holes.
  - UI is absent.
  - Validation metrics are absent.

## Step Audit 2026-04-26 F

- Files added this step:
  - None.
- Files modified this step:
  - `src/mesh2cad/cad/build123d_builder.py`
  - `src/mesh2cad/cad/script_generator.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `python3 -m pip install build123d`
  - `python3 --version`
  - `command -v python3.11 && python3.11 --version`
  - `python3.11 -m pip install build123d && python3.11 -m pip install -e '.[dev]'`
  - `python3.11 - <<'PY' ... PY`
  - `python3.11 - <<'PY' ... PY`
  - `pytest -q`
  - `python3.11 -m pytest -q`
- Tests passed this step:
  - Python 3.14 interpreter: `8 passed, 2 skipped`
  - Python 3.11 interpreter: `8 passed, 2 skipped`
  - Positive-path tests verified under Python 3.11:
    - `tests/test_mesh_pipeline_smoke.py::test_build_step_from_script_writes_step_when_build123d_is_available`
    - `tests/test_mesh_pipeline_smoke.py::test_synthesize_build123d_script_writes_step_when_build123d_is_available`
- Behaviors now physically present:
  - The build runner is compatible with the installed `build123d 0.10.0` API.
  - Generated scripts use `Mode.SUBTRACT` for through-hole sketch subtraction in a way that `build123d` accepts.
  - A real positive-path STEP export has been verified under Python 3.11.
  - The test suite now covers both dependency-missing behavior and successful execution/export behavior.
  - The project now has a known-good interpreter path for CAD execution: Python 3.11.
- Gaps still not physically present:
  - Successful `build123d` execution is not available in the default Python 3.14 interpreter because compatible wheels are unavailable there.
  - The current script generator still only supports rectangular base extrudes and through-holes.
  - UI is absent.
  - Validation metrics are absent.

## Step Audit 2026-04-26 G

- Files added this step:
  - `src/mesh2cad/pipeline/orchestrator.py`
  - `src/mesh2cad/api/__init__.py`
  - `src/mesh2cad/api/service.py`
  - `src/mesh2cad/api/app.py`
- Files modified this step:
  - `src/mesh2cad/main.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `find src/mesh2cad -maxdepth 3 -type f | sort`
  - `sed -n '1,240p' src/mesh2cad/mesh/io.py`
  - `sed -n '1,260p' src/mesh2cad/domain/reports.py`
  - `sed -n '1,360p' tracker.md`
  - `sed -n '1,260p' src/mesh2cad/main.py`
  - `sed -n '1,360p' tests/test_mesh_pipeline_smoke.py`
  - `pytest -q`
  - `python3.11 -m pytest -q`
- Tests passed this step:
  - Python 3.14 interpreter: `11 passed, 2 skipped`
  - Python 3.11 interpreter: `11 passed, 2 skipped`
  - New top-level tests:
    - `tests/test_mesh_pipeline_smoke.py::test_run_pipeline_returns_structured_result_without_build`
    - `tests/test_mesh_pipeline_smoke.py::test_process_mesh_returns_json_friendly_payload`
    - `tests/test_mesh_pipeline_smoke.py::test_cli_outputs_json_payload`
- Behaviors now physically present:
  - The repository now has a pipeline orchestrator that runs load, repair, sample, analyze, primitive fitting, feature inference, and synthesis as one call.
  - The repository now has a Python-callable API service that returns a JSON-friendly response payload.
  - The CLI now calls the API service and prints JSON.
  - An optional FastAPI app factory exists for an HTTP wrapper when FastAPI is installed.
  - The top-level callable surfaces are tested in both interpreters.
- Gaps still not physically present:
  - No actual HTTP server dependency is installed or exercised yet.
  - UI is absent.
  - Validation metrics are absent.
  - The geometry/feature scope is still narrow: rectangular base extrudes plus through-holes.

## Step Audit 2026-04-26 H

- Files added this step:
  - `src/mesh2cad/pipeline/validate.py`
- Files modified this step:
  - `src/mesh2cad/cad/build123d_builder.py`
  - `src/mesh2cad/pipeline/synthesize.py`
  - `src/mesh2cad/pipeline/orchestrator.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,260p' src/mesh2cad/pipeline/orchestrator.py`
  - `sed -n '1,260p' src/mesh2cad/domain/reports.py`
  - `sed -n '1,420p' tests/test_mesh_pipeline_smoke.py`
  - `pytest -q`
  - `python3.11 -m pytest -q`
- Tests passed this step:
  - Python 3.14 interpreter: `11 passed, 3 skipped`
  - Python 3.11 interpreter: `12 passed, 2 skipped`
  - New validation test:
    - `tests/test_mesh_pipeline_smoke.py::test_validate_reconstruction_reports_small_volume_delta_for_box`
- Behaviors now physically present:
  - The repository now has a validation module.
  - Build results now carry metadata including volume and bounding-box extents when available.
  - The orchestrator now attaches a validation report after successful builds.
  - The validation report currently measures first-pass bbox extents delta ratio and volume delta ratio.
  - The API/CLI payloads can now include a concrete validation report when a build is attempted.
- Gaps still not physically present:
  - There is no true surface-distance RMS/max error yet; the current RMS/max fields are populated with bbox extents delta ratio as a temporary proxy.
  - UI is absent.
  - The geometry/feature scope is still narrow: rectangular base extrudes plus through-holes.

## Step Audit 2026-04-26 I

- Files added this step:
  - None.
- Files modified this step:
  - `pyproject.toml`
  - `src/mesh2cad/api/app.py`
  - `src/mesh2cad/api/service.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,240p' pyproject.toml`
  - `sed -n '1,220p' src/mesh2cad/api/app.py`
  - `sed -n '1,260p' src/mesh2cad/api/service.py`
  - `python3.11 - <<'PY' ... PY`
  - `python3.11 -m pip install fastapi uvicorn`
  - `pytest -q`
  - `python3.11 -m pytest -q`
- Tests passed this step:
  - Python 3.14 interpreter: `12 passed, 3 skipped`
  - Python 3.11 interpreter: `13 passed, 2 skipped`
  - New HTTP test:
    - `tests/test_mesh_pipeline_smoke.py::test_http_process_endpoint_returns_json_payload`
- Behaviors now physically present:
  - FastAPI and uvicorn are declared as optional API dependencies.
  - The project has a runnable API entrypoint via `mesh2cad-api`.
  - The HTTP `/process` endpoint is exercised with FastAPI `TestClient`.
  - API responses are now recursively normalized into JSON-safe types, including NumPy arrays and scalars.
  - The server layer is no longer just a factory on disk; it has an exercised request/response path under Python 3.11.
- Gaps still not physically present:
  - The HTTP layer is only exercised under Python 3.11 in this environment.
  - There is no frontend UI yet.
  - There is no true surface-distance RMS/max error yet.
  - The geometry/feature scope is still narrow: rectangular base extrudes plus through-holes.

## Step Audit 2026-04-26 J

- Files added this step:
  - `src/mesh2cad/ui/__init__.py`
  - `src/mesh2cad/ui/state.py`
  - `src/mesh2cad/ui/auth.py`
  - `src/mesh2cad/ui/db.py`
  - `src/mesh2cad/ui/routes.py`
  - `src/mesh2cad/ui/templates/base.html`
  - `src/mesh2cad/ui/templates/login.html`
  - `src/mesh2cad/ui/templates/setup.html`
  - `src/mesh2cad/ui/templates/dashboard.html`
  - `src/mesh2cad/ui/templates/job_detail.html`
  - `src/mesh2cad/ui/static/ui.css`
- Files modified this step:
  - `pyproject.toml`
  - `src/mesh2cad/api/app.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `python3 - <<'PY' ... PY`
  - `python3.11 - <<'PY' ... PY`
  - `python3.11 -m pip install python-multipart`
  - `pytest -q`
  - `python3.11 -m pytest -q`
- Tests passed this step:
  - Python 3.14 interpreter: `13 passed, 3 skipped`
  - Python 3.11 interpreter: `14 passed, 2 skipped`
  - New UI tests:
    - `tests/test_mesh_pipeline_smoke.py::test_ui_setup_login_and_job_flow`
- Behaviors now physically present:
  - The repository now has a server-rendered authenticated web UI.
  - The UI supports first-user bootstrap, session login, logout, upload, job listing, job detail inspection, and artifact download.
  - UI state is persisted locally with SQLite-backed users, sessions, and jobs.
  - Static styling and templates are present on disk.
  - The UI is integrated into the FastAPI app and coexists with the machine API.
- Gaps still not physically present:
  - There is no role matrix beyond authenticated-user access.
  - There is no true surface-distance RMS/max error yet.
  - The geometry/feature scope is still narrow: rectangular base extrudes plus through-holes.

## Step Audit 2026-04-26 K

- Files added this step:
  - None.
- Files modified this step:
  - `src/mesh2cad/cad/build123d_builder.py`
  - `src/mesh2cad/ui/routes.py`
  - `src/mesh2cad/ui/templates/job_detail.html`
  - `src/mesh2cad/ui/static/ui.css`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `python3.11 - <<'PY' ... PY`
  - `sed -n '1,320p' src/mesh2cad/ui/routes.py`
  - `sed -n '1,260p' src/mesh2cad/cad/build123d_builder.py`
  - `pytest -q`
  - `python3.11 -m pytest -q`
- Tests passed this step:
  - Python 3.14 interpreter: `13 passed, 3 skipped`
  - Python 3.11 interpreter: `14 passed, 2 skipped`
  - Preview-related coverage:
    - generated preview STL export metadata
    - UI job detail page includes geometry review section
    - preview artifact download path works when a build is requested
- Behaviors now physically present:
  - Successful CAD builds now export a preview STL alongside STEP.
  - The job detail page now includes a side-by-side geometry review area.
  - The source artifact and generated preview can be rendered in-browser using Three.js loaders.
  - The UI now exposes a concrete visual inspection path instead of only metadata and downloads.
- Gaps still not physically present:
  - Generated preview rendering is limited to browser-supported mesh formats.
  - There is no role matrix beyond authenticated-user access.
  - There is no true surface-distance RMS/max error yet.
  - The geometry/feature scope is still narrow: rectangular base extrudes plus through-holes.

## Step Audit 2026-04-26 L

- Files added this step:
  - `src/mesh2cad/jobs/__init__.py`
  - `src/mesh2cad/jobs/runner.py`
- Files modified this step:
  - `src/mesh2cad/ui/db.py`
  - `src/mesh2cad/ui/routes.py`
  - `src/mesh2cad/api/app.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,320p' src/mesh2cad/ui/db.py`
  - `sed -n '1,360p' src/mesh2cad/ui/routes.py`
  - `sed -n '1,260p' src/mesh2cad/api/app.py`
  - `sed -n '1,260p' src/mesh2cad/api/service.py`
  - `pytest -q`
  - `python3.11 -m pytest -q`
- Tests passed this step:
  - Python 3.14 interpreter: `16 passed, 3 skipped`
  - Python 3.11 interpreter: `17 passed, 2 skipped`
  - New async coverage:
    - `tests/test_mesh_pipeline_smoke.py::test_ui_job_status_endpoint_eventually_completes`
    - `tests/test_mesh_pipeline_smoke.py::test_http_async_process_submission_and_polling`
- Behaviors now physically present:
  - Job execution now runs in a background thread pool instead of the request thread.
  - UI job submission returns immediately and processing continues asynchronously.
  - The API now supports async submission and polling with `/process/submit` and `/process/jobs/{job_id}`.
  - Job state transitions are now visible through dedicated status endpoints.
  - Reports and generated scripts are still written as job artifacts after background completion.
- Gaps still not physically present:
  - There is no external task queue yet.
  - There is no cancellation endpoint yet.
  - There is no retry policy yet.
  - There is no true surface-distance RMS/max error yet.

## Step Audit 2026-04-26 M

- Files added this step:
  - `src/mesh2cad/jobs/worker.py`
- Files modified this step:
  - `src/mesh2cad/jobs/runner.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,260p' src/mesh2cad/jobs/runner.py`
  - `sed -n '1,260p' src/mesh2cad/api/service.py`
  - `sed -n '1,260p' src/mesh2cad/ui/db.py`
  - `sed -n '1,240p' src/mesh2cad/main.py`
  - `pytest -q`
  - `python3.11 -m pytest -q`
- Tests passed this step:
  - Python 3.14 interpreter: `16 passed, 3 skipped`
  - Python 3.11 interpreter: `17 passed, 2 skipped`
- Behaviors now physically present:
  - Background job execution now runs in a subprocess worker instead of directly inside the threadpool worker.
  - The request lifecycle is decoupled from CAD execution at the process boundary.
  - Worker subprocesses write job artifacts and return JSON payloads to the runner.
  - Existing async UI/API polling behavior still works on top of the isolated worker path.
- Gaps still not physically present:
  - There is no external queue or supervisor yet.
  - There is no cancellation endpoint yet.
  - There is no retry policy yet.
  - There is no true surface-distance RMS/max error yet.

## Step Audit 2026-04-26 N

- Files added this step:
  - None.
- Files modified this step:
  - `src/mesh2cad/pipeline/infer_features.py`
  - `src/mesh2cad/cad/script_generator.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,320p' src/mesh2cad/pipeline/infer_features.py`
  - `sed -n '1,260p' src/mesh2cad/domain/features.py`
  - `sed -n '1,260p' src/mesh2cad/cad/script_generator.py`
  - `rg -n "ThroughHoleFeature|BaseExtrudeFeature|infer_features|generate_script" tests/test_mesh_pipeline_smoke.py src/mesh2cad -S`
  - `python3.11 - <<'PY' ... PY`
  - `pytest -q`
  - `python3.11 -m pytest -q`
- Tests passed this step:
  - Python 3.14 interpreter: `17 passed, 3 skipped`
  - Python 3.11 interpreter: `18 passed, 2 skipped`
  - New geometry coverage:
    - `tests/test_mesh_pipeline_smoke.py::test_generate_build123d_script_supports_non_rectangular_polygon`
- Behaviors now physically present:
  - Base extrusion inference now produces a convex polygon loop from projected support points instead of always collapsing to a bounding rectangle.
  - CAD generation now emits `Polygon(*PROFILE)` sketches rather than relying on `Rectangle(WIDTH, HEIGHT)`.
  - Non-rectangular polygonal base profiles are now supported by the generated `build123d` script path.
- Gaps still not physically present:
  - Base profile inference is still convex and does not preserve concave outlines yet.
  - There is no external queue or supervisor yet.
  - There is no cancellation endpoint yet.
  - There is no retry policy yet.
  - There is no true surface-distance RMS/max error yet.

## Step Audit 2026-04-26 O

- Files added this step:
  - None.
- Files modified this step:
  - `src/mesh2cad/pipeline/fit_primitives.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,320p' src/mesh2cad/pipeline/infer_features.py`
  - `sed -n '1,260p' src/mesh2cad/domain/features.py`
  - `sed -n '1,260p' src/mesh2cad/cad/script_generator.py`
  - `rg -n "ThroughHoleFeature|BaseExtrudeFeature|infer_features|generate_script" tests/test_mesh_pipeline_smoke.py src/mesh2cad -S`
  - `python3 - <<'PY' ... PY`
  - `pytest -q`
  - `python3.11 -m pytest -q`
- Tests passed this step:
  - Python 3.14 interpreter: `18 passed, 3 skipped`
  - Python 3.11 interpreter: `19 passed, 2 skipped`
  - New primitive coverage:
    - `tests/test_mesh_pipeline_smoke.py::test_fit_primitives_detects_multiple_cylinders_from_sampled_cloud`
- Behaviors now physically present:
  - Cylinder fitting can now return multiple cylinders from a single sampled cloud.
  - Candidate cylinder centers are inferred from projected normal-line intersections.
  - Cylinder acceptance now uses stronger radius seeding and angular coverage checks to suppress box-like false positives.
- Gaps still not physically present:
  - Multiple-cylinder fitting is still tuned for roughly parallel cylinder axes and mechanical parts.
  - Base profile inference is still convex and does not preserve concave outlines yet.
  - There is no external queue or supervisor yet.
  - There is no cancellation endpoint yet.
  - There is no retry policy yet.
  - There is no true surface-distance RMS/max error yet.

## Step Audit 2026-04-26 P

- Files added this step:
  - None.
- Files modified this step:
  - `src/mesh2cad/pipeline/infer_features.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,260p' src/mesh2cad/pipeline/infer_features.py`
  - `sed -n '1,460p' tests/test_mesh_pipeline_smoke.py`
  - `sed -n '1,260p' src/mesh2cad/cad/script_generator.py`
  - `python3.11 - <<'PY' ... PY`
  - `pytest -q`
  - `python3.11 -m pytest -q`
- Tests passed this step:
  - Python 3.14 interpreter: `20 passed, 3 skipped`
  - Python 3.11 interpreter: `21 passed, 2 skipped`
  - New feature coverage:
    - `tests/test_mesh_pipeline_smoke.py::test_infer_features_detects_multiple_through_holes_and_deduplicates`
    - `tests/test_mesh_pipeline_smoke.py::test_generate_build123d_script_supports_multiple_holes`
- Behaviors now physically present:
  - Through-hole inference now deduplicates near-identical cylinder candidates before emitting CAD features.
  - The feature layer now supports multiple through-hole outputs from one inferred base extrusion.
  - Generated `build123d` scripts now have explicit regression coverage for multiple hole definitions in one sketch.
  - Multi-hole inference is now verified in sketch coordinates using center spacing rather than relying on one fixed sketch-frame orientation.
- Gaps still not physically present:
  - Multi-hole inference is still only validated on a narrow parallel-axis mechanical case.
  - Concave profile inference is not yet validated on noisy real meshes.
  - There is no external queue or supervisor yet.
  - There is no cancellation endpoint yet.
  - There is no retry policy yet.
  - There is no true surface-distance RMS/max error yet.

## Step Audit 2026-04-26 Q

- Files added this step:
  - None.
- Files modified this step:
  - `src/mesh2cad/pipeline/infer_features.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,280p' src/mesh2cad/pipeline/infer_features.py`
  - `sed -n '1,420p' tests/test_mesh_pipeline_smoke.py`
  - `sed -n '1,220p' pyproject.toml`
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k concave`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k concave`
  - `pytest -q`
  - `python3.11 -m pytest -q`
- Tests passed this step:
  - Focused concave-profile regression:
    - Python 3.14 interpreter: `1 passed, 23 deselected`
    - Python 3.11 interpreter: `1 passed, 23 deselected`
  - Full suite:
    - Python 3.14 interpreter: `21 passed, 3 skipped`
    - Python 3.11 interpreter: `22 passed, 2 skipped`
  - New geometry coverage:
    - `tests/test_mesh_pipeline_smoke.py::test_infer_features_preserves_concave_base_profile`
- Behaviors now physically present:
  - Base profile inference now attempts a concave boundary reconstruction from dense planar support before falling back to the convex hull.
  - Concave boundary reconstruction uses Delaunay filtering, a local spacing-derived triangle radius threshold, boundary-loop extraction, and collinearity simplification.
  - The base-extrusion path now preserves at least one class of notched or L-shaped profiles instead of always filling the notch.
  - Concave profile recovery is now regression-tested with an L-shaped synthetic part using profile area as the verification signal.
- Gaps still not physically present:
  - Concave profile inference is not yet validated on noisy real meshes.
  - Multiple-cylinder fitting is still tuned for roughly parallel cylinder axes and mechanical parts.
  - There is no external queue or supervisor yet.
  - There is no cancellation endpoint yet.
  - There is no retry policy yet.
  - Validation is not yet benchmarked on noisy real-world source/build pairs.

## Step Audit 2026-04-26 R

- Files added this step:
  - None.
- Files modified this step:
  - `src/mesh2cad/pipeline/validate.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,260p' src/mesh2cad/pipeline/validate.py`
  - `sed -n '1,280p' src/mesh2cad/pipeline/orchestrator.py`
  - `sed -n '1,260p' src/mesh2cad/domain/reports.py`
  - `rg -n "validate_reconstruction|ValidationReport|rms_error|max_error|volume_delta_ratio|bbox" tests/test_mesh_pipeline_smoke.py src/mesh2cad -S`
  - `python3.11 - <<'PY' ... PY`
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k validate_reconstruction`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k validate_reconstruction`
  - `pytest -q`
  - `python3.11 -m pytest -q`
- Tests passed this step:
  - Focused validation regression:
    - Python 3.14 interpreter: `2 skipped, 23 deselected`
    - Python 3.11 interpreter: `2 passed, 23 deselected`
  - Full suite:
    - Python 3.14 interpreter: `21 passed, 4 skipped`
    - Python 3.11 interpreter: `23 passed, 2 skipped`
  - New validation coverage:
    - `tests/test_mesh_pipeline_smoke.py::test_validate_reconstruction_reports_small_volume_delta_for_box`
    - `tests/test_mesh_pipeline_smoke.py::test_validate_reconstruction_reports_surface_error_for_mismatched_box`
- Behaviors now physically present:
  - Validation now computes sampled bidirectional surface distances between the source mesh and the generated preview STL.
  - `ValidationReport.rms_error` and `ValidationReport.max_error` now represent real geometry deviation when a preview mesh is available, rather than bbox-proxy placeholders.
  - Validation keeps volume and bbox delta ratios as secondary signals alongside the new surface metrics.
  - Surface distance validation works without `rtree` by falling back to `trimesh.proximity.closest_point_naive` in environments that lack the spatial-index dependency.
- Gaps still not physically present:
  - Validation is not yet benchmarked on noisy real-world source/build pairs.
  - Concave profile inference is not yet validated on noisy real meshes.
  - Multiple-cylinder fitting is still tuned for roughly parallel cylinder axes and mechanical parts.
  - There is no external queue or supervisor yet.
  - There is no cancellation endpoint yet.
  - There is no retry policy yet.

## Step Audit 2026-04-26 S

- Files added this step:
  - None.
- Files modified this step:
  - `src/mesh2cad/pipeline/fit_primitives.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,360p' src/mesh2cad/pipeline/fit_primitives.py`
  - `sed -n '220,340p' src/mesh2cad/pipeline/fit_primitives.py`
  - `sed -n '1,220p' src/mesh2cad/mesh/sampling.py`
  - `python3.11 - <<'PY' ... PY`
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k noisy_multi_hole`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k noisy_multi_hole`
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k "detects_cylinder or noisy_multi_hole"`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k "detects_cylinder or noisy_multi_hole"`
  - `pytest -q`
  - `python3.11 -m pytest -q`
- Tests passed this step:
  - Focused noisy multi-hole regression:
    - Python 3.14 interpreter: `1 passed, 25 deselected`
    - Python 3.11 interpreter: `1 passed, 25 deselected`
  - Focused cylinder/noisy-part regression:
    - Python 3.14 interpreter: `2 passed, 24 deselected`
    - Python 3.11 interpreter: `2 passed, 24 deselected`
  - Full suite:
    - Python 3.14 interpreter: `22 passed, 4 skipped`
    - Python 3.11 interpreter: `24 passed, 2 skipped`
  - New robustness coverage:
    - `tests/test_mesh_pipeline_smoke.py::test_fit_primitives_and_infer_features_handle_noisy_multi_hole_part`
- Behaviors now physically present:
  - Cylinder fitting now prefers the residual non-planar cloud after plane extraction when enough residual support exists.
  - Residual cylinder fitting now clusters sidewall support spatially before candidate-center inference, which suppresses cross-hole false cylinders on noisy multi-hole parts.
  - Cylinder fitting falls back to the full cloud when plane over-coverage would leave too little residual support, preserving the standalone-cylinder case.
  - The backend now has explicit regression coverage for a noisy two-hole prismatic part that exercises primitive fitting and feature inference together.
- Gaps still not physically present:
  - Noisy robustness is not yet validated on scanned real-world parts.
  - Concave profile inference is not yet validated on noisy real meshes.
  - Multiple-cylinder fitting is still tuned for roughly parallel cylinder axes and mechanical parts.
  - There is no external queue or supervisor yet.
  - There is no cancellation endpoint yet.
  - There is no retry policy yet.

## Step Audit 2026-04-26 T

- Files added this step:
  - None.
- Files modified this step:
  - `src/mesh2cad/pipeline/fit_primitives.py`
  - `src/mesh2cad/pipeline/infer_features.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,220p' src/mesh2cad/mesh/io.py`
  - `sed -n '1,240p' src/mesh2cad/mesh/cleanup.py`
  - `sed -n '1,220p' src/mesh2cad/pipeline/orchestrator.py`
  - `python3.11 - <<'PY' ... PY`
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k scan_like_noisy_multi_hole_mesh`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k scan_like_noisy_multi_hole_mesh`
  - `pytest -q`
  - `python3.11 -m pytest -q`
- Tests passed this step:
  - Focused scan-like mesh regression:
    - Python 3.14 interpreter: `1 skipped, 26 deselected`
    - Python 3.11 interpreter: `1 passed, 26 deselected`
  - Full suite:
    - Python 3.14 interpreter: `22 passed, 5 skipped`
    - Python 3.11 interpreter: `25 passed, 2 skipped`
  - New real-mesh coverage:
    - `tests/test_mesh_pipeline_smoke.py::test_run_pipeline_handles_scan_like_noisy_multi_hole_mesh`
- Behaviors now physically present:
  - The test suite now includes a scan-like triangulated mesh fixture generated from a real extruded CAD part and degraded with vertex noise before re-import.
  - The real mesh path now has explicit regression coverage through `run_pipeline`, not just direct point-cloud or primitive-layer checks.
  - Cylinder acceptance is stricter on angular support coverage, which reduces false cylinder hypotheses on noisy triangulated inputs.
  - Through-hole inference now has crowded-candidate post-filtering, and the scan-like mesh regression verifies that the pipeline can recover a base extrusion plus at least two plausible through-hole features from a noisy triangulated part.
- Gaps still not physically present:
  - The scan-like mesh regression does not yet guarantee exact recovery of only the true hole set.
  - Noisy robustness is not yet validated on scanned real-world parts.
  - Concave profile inference is not yet validated on noisy real meshes.
  - Multiple-cylinder fitting is still tuned for roughly parallel cylinder axes and mechanical parts.
  - There is no external queue or supervisor yet.
  - There is no cancellation endpoint yet.
  - There is no retry policy yet.

## Step Audit 2026-04-26 U

- Files added this step:
  - None.
- Files modified this step:
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,240p' tests/test_mesh_pipeline_smoke.py`
  - `sed -n '240,520p' tests/test_mesh_pipeline_smoke.py`
  - `sed -n '520,940p' tests/test_mesh_pipeline_smoke.py`
  - `python3.11 - <<'PY' ... PY`
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k artifact_matrix`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k artifact_matrix`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k "artifact_matrix and not face_dropout"`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k "artifact_matrix and face_dropout"`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k "artifact_matrix or ui_setup_login_and_job_flow"`
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k "artifact_matrix or ui_setup_login_and_job_flow"`
  - `pytest -q`
  - `python3.11 -m pytest -q`
- Tests passed this step:
  - Focused artifact matrix:
    - Python 3.14 interpreter: `6 skipped, 27 deselected`
    - Python 3.11 interpreter split runs:
      - `5 passed, 28 deselected`
      - `1 passed, 32 deselected`
  - Targeted rerun:
    - Python 3.14 interpreter: `1 passed, 6 skipped, 26 deselected`
    - Python 3.11 interpreter: `7 passed, 26 deselected`
  - Full suite:
    - Python 3.14 interpreter: `22 passed, 11 skipped`
    - Python 3.11 interpreter: `31 passed, 2 skipped`
  - New artifact coverage:
    - `tests/test_mesh_pipeline_smoke.py::test_run_pipeline_artifact_matrix_recovers_expected_features`
- Behaviors now physically present:
  - The test suite now includes a parameterized artifact matrix over mesh artifact kind, artifact magnitude, and part scale for the real triangulated mesh pipeline path.
  - The matrix distinguishes supported recovery cases from degraded-but-structured cases instead of forcing every artifact cell into one threshold.
  - Supported cases currently include mild and moderate Gaussian vertex noise, sparse outliers, and a larger-scale Gaussian-noise part with recovery of the base extrusion plus at least two hole features.
  - Degraded-but-structured cases currently include strong quantization and mild face dropout, where the pipeline is expected to recover the base extrusion while explicitly missing through-hole recovery.
  - The artifact sweep is now deterministic for regression purposes through fixed seeds on mesh degradation and pipeline sampling.
- Gaps still not physically present:
  - The artifact matrix does not yet include true scanned meshes from external datasets or real shop/consumer scans.
  - The artifact matrix does not yet cover non-prismatic parts or non-parallel hole axes.
  - The degraded artifact cases are not yet promoted into the fully supported recovery tier.
  - There is no external queue or supervisor yet.
  - There is no cancellation endpoint yet.
  - There is no retry policy yet.

## Step Audit 2026-04-27 A

- Files added this step:
  - None.
- Files modified this step:
  - `src/mesh2cad/domain/features.py`
  - `src/mesh2cad/cad/script_generator.py`
  - `src/mesh2cad/cad/build123d_builder.py`
  - `src/mesh2cad/pipeline/infer_features.py`
  - `src/mesh2cad/pipeline/validate.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,260p' tests/test_mesh_pipeline_smoke.py`
  - `sed -n '1,260p' tracker.md`
  - `sed -n '1,220p' src/mesh2cad/cad/script_generator.py`
  - `sed -n '260,620p' tests/test_mesh_pipeline_smoke.py`
  - `sed -n '220,520p' tracker.md`
  - `sed -n '1,220p' src/mesh2cad/pipeline/validate.py`
  - `sed -n '620,980p' tests/test_mesh_pipeline_smoke.py`
  - `sed -n '1,220p' src/mesh2cad/cad/build123d_builder.py`
  - `sed -n '1,220p' src/mesh2cad/domain/features.py`
  - `sed -n '1,220p' src/mesh2cad/domain/types.py`
  - `rg -n "def _infer_bosses|def _infer_through_holes|height_estimate|through holes inferred|BossFeature" src/mesh2cad/pipeline/infer_features.py`
  - `sed -n '132,260p' src/mesh2cad/pipeline/infer_features.py`
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k 'cylindrical_boss or supports_bosses or l_bracket or invalid_solid_warning'`
  - `python3 - <<'PY' ... PY`
  - `sed -n '1,120p' src/mesh2cad/pipeline/orchestrator.py`
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k 'cylindrical_boss or supports_bosses or l_bracket or invalid_solid_warning'`
  - `pytest -q`
  - `python3.11 -m pytest -q`
- Tests passed this step:
  - Focused tracker-goal coverage:
    - `tests/test_mesh_pipeline_smoke.py::test_infer_features_detects_cylindrical_boss`
    - `tests/test_mesh_pipeline_smoke.py::test_generate_build123d_script_supports_bosses`
    - `tests/test_mesh_pipeline_smoke.py::test_run_pipeline_recovers_l_bracket_fixture_without_build`
    - `tests/test_mesh_pipeline_smoke.py::test_validate_reconstruction_reports_invalid_solid_warning_from_metadata`
  - Full suite:
    - Python 3.14 interpreter: `42 passed, 11 skipped`
    - Python 3.11 interpreter: `51 passed, 2 skipped`
- Behaviors now physically present:
  - Boss feature inference exists for short cylinders aligned to the base extrusion axis.
  - The generated `build123d` script format can now express cylindrical bosses in addition to base extrudes and through-holes.
  - CAD build metadata now carries kernel-level solid validity and manifoldness flags into validation.
  - Validation now emits explicit warnings when the CAD kernel reports an invalid or non-manifold solid.
  - The test suite now includes a mesh-backed L-bracket fixture that runs through the actual pipeline and verifies a concave polygonal base profile path.
  - The repository already had CI, and the tracker now reflects the existing GitHub Actions workflow instead of leaving that goal incorrectly open.
- Gaps still not physically present:
  - Pocket inference is still absent.
  - Sphere primitive fitting is still absent.
  - The L-bracket fixture does not yet include hole or boss variants.
  - CI is present, but there is no evidence in the repo itself of remote GitHub run status history.
  - There is still no cancellation endpoint, retry policy, or external job supervisor.

## Step Audit 2026-04-27 B

- Files added this step:
  - None.
- Files modified this step:
  - `src/mesh2cad/domain/primitives.py`
  - `src/mesh2cad/pipeline/fit_primitives.py`
  - `src/mesh2cad/cad/script_generator.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,360p' src/mesh2cad/pipeline/fit_primitives.py`
  - `sed -n '1,220p' src/mesh2cad/domain/primitives.py`
  - `rg -n "Cone|PrimitiveKind.CONE|cone primitive|cone" tests/test_mesh_pipeline_smoke.py tracker.md src/mesh2cad -g '!*.pyc'`
  - `sed -n '360,760p' src/mesh2cad/pipeline/fit_primitives.py`
  - `sed -n '1,220p' src/mesh2cad/pipeline/orchestrator.py`
  - `sed -n '1,220p' src/mesh2cad/domain/reports.py`
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k 'detects_cone'`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k 'detects_cone'`
  - `pytest -q`
  - `python3.11 -m pytest -q`
  - `rg -n "BLIND_HOLES|POCKETS|blind hole|PocketFeature|BlindHoleFeature|boss_plane = Plane|origin=ORIGIN \\+ \\(Z_DIR \\*\" src/mesh2cad/cad/script_generator.py tests/test_mesh_pipeline_smoke.py`
  - `sed -n '1,320p' src/mesh2cad/cad/script_generator.py`
  - `python3.11 - <<'PY' ... PY`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k 'blind_hole_and_pocket_build or detects_cone or supports_bosses'`
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k 'detects_cone or supports_bosses'`
- Tests passed this step:
  - Focused cone coverage:
    - `tests/test_mesh_pipeline_smoke.py::test_fit_primitives_detects_cone`
  - Focused generator/build regression coverage:
    - `tests/test_mesh_pipeline_smoke.py::test_generate_script_blind_hole_and_pocket_build`
    - `tests/test_mesh_pipeline_smoke.py::test_generate_build123d_script_supports_bosses`
  - Full suite:
    - Python 3.14 interpreter: `43 passed, 12 skipped`
    - Python 3.11 interpreter: `53 passed, 2 skipped`
- Behaviors now physically present:
  - The primitive fitter can now emit `ConePrimitive` results from sampled sidewall geometry.
  - Cone fitting reuses the existing sidewall clustering and axis-estimation path, then validates a linear taper in radius along the inferred axis.
  - Cone primitives now include apex, axis direction, base radius, top radius, semi-angle, height estimate, support region, and confidence.
  - The test suite now verifies cone detection on a synthetic cone mesh in both interpreters.
  - The pose-aware CAD script generator now uses explicit tuple math for translated sketch planes, which fixes build execution for blind-hole and pocket scripts under Python 3.11.
- Gaps still not physically present:
  - Cone fitting is not yet consumed by downstream feature inference.
  - Pocket inference is still absent.
  - There is still no cancellation endpoint, retry policy, or external job supervisor.

## Step Audit 2026-04-27 C

- Files added this step:
  - None.
- Files modified this step:
  - `src/mesh2cad/domain/primitives.py`
  - `src/mesh2cad/pipeline/fit_primitives.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,260p' src/mesh2cad/domain/primitives.py`
  - `sed -n '1,420p' src/mesh2cad/pipeline/fit_primitives.py`
  - `rg -n "sphere|PrimitiveKind.SPHERE|Sphere" tests/test_mesh_pipeline_smoke.py tracker.md src/mesh2cad -g '!*.pyc'`
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k 'detects_sphere'`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k 'detects_sphere'`
  - `pytest -q`
  - `python3.11 -m pytest -q`
- Tests passed this step:
  - Focused sphere coverage:
    - `tests/test_mesh_pipeline_smoke.py::test_fit_primitives_detects_sphere`
  - Full suite:
    - Python 3.14 interpreter: `44 passed, 13 skipped`
    - Python 3.11 interpreter: `55 passed, 2 skipped`
- Behaviors now physically present:
  - The primitive fitter can now emit `SpherePrimitive` results from sampled mesh geometry.
  - Sphere fitting uses sampled point normals to solve for a shared center and radius, then validates support residuals, radius consistency, and directional coverage before accepting a primitive.
  - Sphere primitives now include center, radius, support region, area estimate, and confidence.
  - The test suite now verifies sphere detection on a synthetic sphere mesh in both interpreters.
- Gaps still not physically present:
  - Sphere fitting is not yet consumed by downstream feature inference.
  - Cone fitting is not yet consumed by downstream feature inference.
  - There is still no cancellation endpoint, retry policy, or external job supervisor.

## Step Audit 2026-04-27 D

- Files added this step:
  - None.
- Files modified this step:
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,260p' src/mesh2cad/domain/features.py`
  - `rg -n "PocketFeature|BLIND_HOLE|POCKET|pocket inference|blind hole" src/mesh2cad tests/test_mesh_pipeline_smoke.py tracker.md`
  - `sed -n '1,340p' src/mesh2cad/pipeline/infer_features.py`
  - `sed -n '340,620p' src/mesh2cad/pipeline/infer_features.py`
  - `sed -n '1080,1215p' tests/test_mesh_pipeline_smoke.py`
  - `sed -n '220,260p' tracker.md`
  - `python3 - <<'PY' ... PY`
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k 'detects_planar_pocket or blind_hole_and_pocket_build'`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k 'detects_planar_pocket or blind_hole_and_pocket_build'`
  - `pytest -q`
  - `python3.11 -m pytest -q`
- Tests passed this step:
  - Focused pocket coverage:
    - `tests/test_mesh_pipeline_smoke.py::test_infer_features_detects_planar_pocket`
    - `tests/test_mesh_pipeline_smoke.py::test_generate_script_blind_hole_and_pocket_build`
  - Full suite:
    - Python 3.14 interpreter: `46 passed, 13 skipped`
    - Python 3.11 interpreter: `57 passed, 2 skipped`
- Behaviors now physically present:
  - Pocket inference is verified on a synthetic planar cutout case.
  - The feature inference layer can emit `PocketFeature` objects from paired interior parallel planes within a base extrusion.
  - The existing CAD script path for pockets remains buildable under the Python 3.11 build-enabled environment.
- Gaps still not physically present:
  - Sphere and cone primitives are still not consumed by downstream feature inference.
  - There is still no cancellation endpoint, retry policy, or external job supervisor.

## Step Audit 2026-04-27 E

- Files added this step:
  - None.
- Files modified this step:
  - `src/mesh2cad/ui/db.py`
  - `src/mesh2cad/jobs/runner.py`
  - `src/mesh2cad/api/schemas.py`
  - `src/mesh2cad/api/app.py`
  - `src/mesh2cad/ui/routes.py`
  - `src/mesh2cad/ui/templates/job_detail.html`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,280p' src/mesh2cad/jobs/runner.py`
  - `sed -n '1,260p' src/mesh2cad/jobs/worker.py`
  - `sed -n '1,320p' src/mesh2cad/ui/db.py`
  - `sed -n '1,320p' src/mesh2cad/api/app.py`
  - `sed -n '1,260p' src/mesh2cad/api/schemas.py`
  - `rg -n "cancel|submit|jobs/|queued|processing|failed|completed|retry" tests/test_mesh_pipeline_smoke.py src/mesh2cad/ui/routes.py src/mesh2cad/api/app.py`
  - `sed -n '1,360p' src/mesh2cad/ui/routes.py`
  - `sed -n '1,260p' src/mesh2cad/jobs/worker_subprocess.py`
  - `sed -n '1,220p' src/mesh2cad/jobs/exceptions.py`
  - `sed -n '1360,1575p' tests/test_mesh_pipeline_smoke.py`
  - `sed -n '1,220p' src/mesh2cad/api/service.py`
  - `rg -n "can_cancel|cancel|Retry|retry" src/mesh2cad/ui/templates/job_detail.html src/mesh2cad/ui/templates/dashboard.html`
  - `sed -n '1,260p' src/mesh2cad/ui/templates/job_detail.html`
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k 'retry_after_completion or cancel_when_still_queued'`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k 'retry_after_completion or cancel_when_still_queued'`
  - `pytest -q`
  - `python3.11 -m pytest -q`
- Tests passed this step:
  - Focused async control coverage:
    - `tests/test_mesh_pipeline_smoke.py::test_http_process_job_cancel_when_still_queued`
    - `tests/test_mesh_pipeline_smoke.py::test_http_async_process_retry_after_completion`
    - `tests/test_mesh_pipeline_smoke.py::test_ui_job_retry_after_completion`
  - Full suite:
    - Python 3.14 interpreter: `49 passed, 13 skipped`
    - Python 3.11 interpreter: `60 passed, 2 skipped`
- Behaviors now physically present:
  - Job request parameters are now persisted in the database for durable retry.
  - Async API jobs can be cancelled through `/process/jobs/{job_id}/cancel`.
  - Async API jobs can be retried through `/process/jobs/{job_id}/retry`.
  - Authenticated UI jobs can be retried through `/jobs/{job_id}/retry`.
  - Retrying a job clears previous artifacts, bumps retry metadata, and resubmits the same persisted request on the same job ID.
  - Queued/running jobs now transition through explicit cancellation handling instead of only relying on passive worker cleanup.
- Gaps still not physically present:
  - There is still no external queue or supervisor.
  - Cone and sphere primitives are still not consumed by downstream feature inference.

## Step Audit 2026-04-27 F

- Files added this step:
  - None.
- Files modified this step:
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,260p' README.md`
  - `sed -n '340,520p' tracker.md`
  - `tail -n 120 tracker.md`
  - `rg -n "FeatureKind|class .*Feature|def infer_|supported|roadmap|Next|TODO|unchecked|\\[ \\]" src tests docs README.md tracker.md`
- Tests passed this step:
  - None; this step was tracker reconciliation and backlog shaping only.
- Behaviors now physically present:
  - The tracker now reflects the broader feature surface already present in the repository, including countersinks, blind holes, spherical modifiers, revolve support, and richer CAD synthesis coverage.
  - The tracker now contains a concrete breadth-expansion queue focused on new mechanical workflows rather than only incremental polishing.
  - The next-wave product backlog is now organized around hole stacks, counterbores, tapered features, multi-face prismatic parts, multi-body handling, point-cloud-native coverage, and broader rotational workflows.
- Gaps still not physically present:
  - The new breadth-expansion items remain backlog items and are not implemented yet.
  - There is still no external queue or supervisor.

## Step Audit 2026-04-27 G

- Files added this step:
  - None.
- Files modified this step:
  - `src/mesh2cad/domain/types.py`
  - `src/mesh2cad/domain/features.py`
  - `src/mesh2cad/pipeline/infer_features.py`
  - `src/mesh2cad/cad/script_generator.py`
  - `src/mesh2cad/mesh/sampling.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '1,220p' src/mesh2cad/domain/features.py`
  - `sed -n '1,260p' src/mesh2cad/domain/types.py`
  - `sed -n '1,420p' src/mesh2cad/pipeline/infer_features.py`
  - `sed -n '1,360p' src/mesh2cad/cad/script_generator.py`
  - `rg -n "COUNTERSINK|counterbore|blind hole|ThroughHoleFeature|BlindHoleFeature|CounterSinkHoleFeature|Hole" tests/test_mesh_pipeline_smoke.py src/mesh2cad -g '!*.pyc'`
  - `python3.11 - <<'PY' ... PY` to inspect `build123d` hole helpers
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k 'hole_stack or countersink or counterbore'`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k 'hole_stack or countersink or counterbore'`
  - `python3.11 -m pytest -q tests/test_benchmarks.py -k 'two_hole_plate_prismatic_through_holes'`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k 'generated_angled_hole_script_is_buildable or hole_stack or counterbore'`
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k 'hole_stack or counterbore'`
  - `pkill -f ...` cleanup for stale `pytest` and worker processes
- Tests passed this step:
  - `tests/test_mesh_pipeline_smoke.py::test_infer_features_detects_countersink_hole_stack`
  - `tests/test_mesh_pipeline_smoke.py::test_generate_build123d_script_supports_countersink_hole_stack`
  - `tests/test_mesh_pipeline_smoke.py::test_generate_build123d_script_supports_counterbore_hole_stack`
  - `tests/test_mesh_pipeline_smoke.py::test_generated_angled_hole_script_is_buildable`
  - `tests/test_benchmarks.py::test_benchmark_cases_meet_expectations[two_hole_plate_prismatic_through_holes]`
  - Focused aggregate commands listed above all passed.
- Behaviors now physically present:
  - The domain model now includes a structured `HoleStackFeature` with axial `HoleSection` records and explicit hole termination semantics.
  - Feature inference now composes existing through-hole, blind-hole, and countersink detections into structured hole stacks without removing the current feature-specific outputs.
  - The CAD script generator now understands hole stacks and can decompose supported stack patterns back into executable build123d operations.
  - Countersink hole stacks are now supported as one cone section plus one cylindrical section on a shared axis.
  - Counterbore-style stepped cylindrical stacks are now supported in generated CAD output via `CounterBoreHole`.
  - Hole inference is more robust on noisy stock profiles because hole-fit checks now fall back to an outer profile envelope when the detailed loop is too irregular.
  - Surface sampling is now deterministic for repeatable benchmark and inference behavior on the same mesh input.
  - The angled through-hole build path was corrected so the generated script builds successfully under the build-enabled environment.
- Gaps still not physically present:
  - Counterbore inference does not yet exist as a native downstream inference route from fitted primitives.
  - Tapered blind-hole and tapered boss inference are still backlog items.
  - There is still no external queue or supervisor.

## Step Audit 2026-04-27 H

- Files added this step:
  - None.
- Files modified this step:
  - `src/mesh2cad/pipeline/infer_features.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `sed -n '500,760p' src/mesh2cad/pipeline/infer_features.py`
  - `sed -n '1,260p' src/mesh2cad/domain/features.py`
  - `rg -n "counterbore|HoleStackFeature|BlindHoleFeature|COUNTERBORE_HOLES|hole stack" tests src/mesh2cad -g '!*.pyc'`
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k 'counterbore_hole_stack'`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k 'counterbore_hole_stack'`
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k 'hole_stack or counterbore or countersink_hole_stack'`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k 'hole_stack or counterbore or countersink_hole_stack'`
- Tests passed this step:
  - `tests/test_mesh_pipeline_smoke.py::test_infer_features_detects_counterbore_hole_stack`
  - `tests/test_mesh_pipeline_smoke.py::test_generate_build123d_script_supports_counterbore_hole_stack`
  - `tests/test_mesh_pipeline_smoke.py::test_generate_build123d_script_supports_countersink_hole_stack`
  - Focused aggregate commands listed above all passed in both interpreters.
- Behaviors now physically present:
  - The feature inference layer can now detect a native counterbore-style stepped hole from a shallow large cylinder paired with a deeper coaxial through-hole cylinder.
  - Counterbore inference emits a structured `HoleStackFeature` with two cylindrical sections on a shared axis.
  - The existing CAD script generator already consumes that inferred stack and reconstructs it as a `CounterBoreHole`.
  - Counterbore inference is now verified with a synthetic primitive-backed stepped-bore test in both interpreters.
- Gaps still not physically present:
  - Tapered blind-hole inference is still absent.
  - Tapered boss inference is still absent.
  - There is still no external queue or supervisor.

## Step Audit 2026-04-27 I

- Files added this step:
  - None.
- Files modified this step:
  - `src/mesh2cad/pipeline/infer_features.py`
  - `src/mesh2cad/cad/script_generator.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `rg -n "CounterSinkHole\\(|COUNTERSINK_HOLES|ANGLED_COUNTERSINKS|HoleStackFeature|_stack_is_countersink|BLIND_HOLE" src/mesh2cad/cad/script_generator.py src/mesh2cad/pipeline/infer_features.py tests/test_mesh_pipeline_smoke.py`
  - `python3.11 - <<'PY' ... PY` to confirm `CounterSinkHole` signature supports finite `depth`
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k 'tapered_blind_hole_stack'`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k 'tapered_blind_hole_stack'`
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k 'hole_stack or counterbore_hole_stack or tapered_blind_hole_stack or countersink_hole_stack'`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k 'hole_stack or counterbore_hole_stack or tapered_blind_hole_stack or countersink_hole_stack'`
- Tests passed this step:
  - `tests/test_mesh_pipeline_smoke.py::test_infer_features_detects_tapered_blind_hole_stack`
  - `tests/test_mesh_pipeline_smoke.py::test_generate_build123d_script_supports_tapered_blind_hole_stack`
  - Focused aggregate commands listed above all passed in both interpreters.
- Behaviors now physically present:
  - The feature inference layer can now detect a tapered blind hole from a cone primitive matched to a blind cylindrical hole on a shared axis.
  - Tapered blind-hole inference emits a structured blind `HoleStackFeature` with one cone section followed by one cylindrical section.
  - The CAD script generator now consumes blind cone+cylinder stacks and reconstructs them with `CounterSinkHole(..., depth=blind_depth)`.
  - The tapered blind route is verified both at feature-inference level and generated-script level.
- Gaps still not physically present:
  - Tapered boss inference is still absent.
  - There is still no external queue or supervisor.

## Step Audit 2026-04-27 J

- Files added this step:
  - None.
- Files modified this step:
  - `src/mesh2cad/domain/types.py`
  - `src/mesh2cad/domain/features.py`
  - `src/mesh2cad/pipeline/infer_features.py`
  - `src/mesh2cad/cad/script_generator.py`
  - `tests/test_mesh_pipeline_smoke.py`
  - `tracker.md`
- Commands run this step:
  - `rg -n "BossFeature|_infer_bosses|ConePrimitive|boss" src/mesh2cad/pipeline/infer_features.py src/mesh2cad/cad/script_generator.py src/mesh2cad/domain/features.py tests/test_mesh_pipeline_smoke.py`
  - `python3.11 - <<'PY' ... PY` to inspect `Cone` and `loft` build123d primitives
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k 'tapered_boss'`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k 'tapered_boss'`
  - `pytest -q tests/test_mesh_pipeline_smoke.py -k 'tapered_boss or bosses or tapered_blind_hole_stack or counterbore_hole_stack or countersink_hole_stack'`
  - `python3.11 -m pytest -q tests/test_mesh_pipeline_smoke.py -k 'tapered_boss or bosses or tapered_blind_hole_stack or counterbore_hole_stack or countersink_hole_stack'`
- Tests passed this step:
  - `tests/test_mesh_pipeline_smoke.py::test_infer_features_detects_tapered_boss`
  - `tests/test_mesh_pipeline_smoke.py::test_generate_build123d_script_supports_tapered_bosses`
  - Focused aggregate commands listed above all passed in both interpreters.
- Behaviors now physically present:
  - The domain model now includes a `TaperedBossFeature`.
  - The feature inference layer can now detect tapered outward cone-backed protrusions from a stock face.
  - Tapered boss inference emits an additive feature with base radius, top radius, height, face attachment, and start offset.
  - The CAD script generator now reconstructs tapered bosses with additive `loft` geometry between two circular sketches.
  - Tapered boss inference and CAD generation are both covered by focused tests.
- Gaps still not physically present:
  - There is still no external queue or supervisor.
