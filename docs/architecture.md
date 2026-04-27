# Architecture

## Purpose

ViminCADConverter is a local-first Python system for recovering lightweight mechanical CAD structure from triangle meshes and dense point inputs. The current codebase is optimized for:

- prismatic mechanical parts with dominant planar stock and through-holes
- a first rotational route driven by strong cylinder primitives
- script-first CAD output through `build123d`

The implementation is organized as a staged pipeline with a thin API/UI layer on top.

## Top-level layers

### Geometry input and normalization

Modules:

- `src/mesh2cad/mesh/io.py`
- `src/mesh2cad/mesh/cleanup.py`
- `src/mesh2cad/mesh/sampling.py`
- `src/mesh2cad/mesh/analysis.py`

Responsibilities:

- load mesh files into a normalized `trimesh.Trimesh`
- apply conservative cleanup without aggressively reshaping the part
- sample surface points and normals for downstream inference
- extract coarse global structure such as principal axes and part class hints

### Geometric inference

Modules:

- `src/mesh2cad/pipeline/fit_primitives.py`
- `src/mesh2cad/pipeline/infer_features.py`
- `src/mesh2cad/pipeline/infer_revolve.py`

Responsibilities:

- recover primitive hypotheses such as planes and cylinders
- infer higher-level CAD-like features from primitive relationships
- choose between the current prismatic and rotational routes

Current route split:

- prismatic route: paired planes -> extrusion profile -> through-hole candidates
- rotational route: dominant cylinder -> revolve feature -> pose-aware revolve script

### CAD synthesis and export

Modules:

- `src/mesh2cad/cad/script_generator.py`
- `src/mesh2cad/cad/build123d_builder.py`
- `src/mesh2cad/cad/export.py`

Responsibilities:

- convert inferred features into `build123d` source
- execute generated code when `build123d` is available
- export `STEP` and preview `STL`
- attach build metadata such as volume and extents

### Validation

Modules:

- `src/mesh2cad/pipeline/validate.py`

Responsibilities:

- compare source geometry against generated preview geometry
- expose volume delta, bbox delta, surface RMS error, and surface max error
- keep validation usable in environments without `rtree`

### Orchestration and plan reporting

Modules:

- `src/mesh2cad/pipeline/orchestrator.py`
- `src/mesh2cad/domain/plan.py`

Responsibilities:

- run the full pipeline from input path to synthesized output
- emit a structured result object for API, CLI, and worker use
- keep stage-level route/plan information observable

### Service, API, jobs, and UI

Modules:

- `src/mesh2cad/api/`
- `src/mesh2cad/jobs/`
- `src/mesh2cad/ui/`

Responsibilities:

- expose synchronous and asynchronous processing entrypoints
- run background work in subprocess-backed jobs
- persist users, sessions, jobs, and artifacts
- provide an authenticated technical UI for upload, review, and download

## Data flow

```text
mesh/points
-> load + repair
-> sample + analyze
-> primitive fitting
-> feature inference or revolve inference
-> build123d script synthesis
-> optional execution/export
-> validation
-> API/UI/job artifacts
```

## Core domain objects

Important dataclasses live under `src/mesh2cad/domain/`:

- `PrimitiveKind`, `FeatureKind`, `PartClass`, `ToleranceConfig`
- `PlanePrimitive`, `CylinderPrimitive`
- `BaseExtrudeFeature`, `ThroughHoleFeature`, `RevolveSolidFeature`
- `DetectionReport`, `ValidationReport`
- `ReconstructionPlan`, `PlanStage`

These types are the stable interface between inference, synthesis, validation, and presentation layers.

## Current architectural constraints

- Primitive fitting is still heuristic-first, not ML-driven.
- Cylinder fitting is tuned for roughly parallel hole/stock configurations.
- Concave profile recovery is first-pass and only lightly stress-tested.
- Dense point inputs are supported, but the benchmark/test corpus is still dominated by synthetic and scan-like mesh fixtures.
- Background execution is subprocess-based, but there is no durable external queue yet.

## Near-term technical pressure points

- stronger primitive segmentation on quantized and partially missing meshes
- better true-hole discrimination on noisy triangulated inputs
- real scan fixtures and benchmark expansion
- richer invalid-solid and structured failure reporting
- optional durable job backend
