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

- recover primitive hypotheses such as planes, cylinders, and cones
- infer higher-level CAD-like features from primitive relationships:
  - `ThroughHoleFeature`: cylinder primitives; includes angled/non-parallel axes when the cylinder axis crosses the inferred stock faces (detected via plane-to-plane face analysis)
  - `CounterSinkHoleFeature`: cone primitives paired with through-holes; supports angled countersinks aligned to their parent hole axes
  - `BlindHoleFeature`: cylinder primitives with axis origin and direction; supports both aligned (axis parallel to extrusion) and angled configurations
  - `BaseExtrudeFeature`: paired parallel planes define the stock base shape and extrusion profile
  - `RevolveSolidFeature`: single dominant cylinder inferred as a revolve axis (rotational route only)
- choose between prismatic and rotational routes based on inferred feature types and part class analysis

**Route selection logic:**

- **Prismatic route** (preferred): paired planes → extrusion profile → feature candidates (holes, bosses)
  - triggers when base extrusion feature extraction succeeds
  - through-holes, countersinks, and blind holes are inferred; angled variants are supported when geometric constraints permit
  - route remains preferred even if revolve route is available (favors prismatic interpretations)

- **Rotational route** (fallback): single strong cylinder → revolve feature + pose-aware script
  - triggers when `part_class == PartClass.ROTATIONAL` OR no prismatic base extraction succeeds
  - mutually exclusive with prismatic route in final output

**Angled feature inference:**

- **Angled through-holes**: a cylinder primitive axis is checked for intersection with the inferred top and bottom stock faces; if both are crossed, the hole is treated as non-parallel and stored with `axis_origin` and `axis_direction`
- **Angled countersinks**: when a cone primitive matches a through-hole (same entry region on top face), the cone's axis is aligned to the hole's axis
- **Angled blind holes**: a cylinder primitive not aligned with the extrusion axis is inferred as a blind hole with explicit axis fields; depth is measured along the axis direction

Current route split:

- prismatic route: paired planes → extrusion profile → through-hole candidates (aligned or angled), countersinks, blind holes
- rotational route: dominant cylinder → revolve feature → pose-aware revolve script

### CAD synthesis and export

Modules:

- `src/mesh2cad/cad/script_generator.py`
- `src/mesh2cad/cad/build123d_builder.py`
- `src/mesh2cad/cad/export.py`

Responsibilities:

- convert inferred features into `build123d` source code:
  - **aligned through-holes**: simple Hole() calls with standard sketch-plane depth
  - **angled through-holes**: create a pose-aware sketch plane perpendicular to the hole axis; drill through-hole along that local frame
  - **countersinks**: paired with through-holes; angled countersinks use the parent hole's axis plane
  - **blind holes**: cylinder-based pockets; angled blind holes generate pose-aware sketches and hole depth measured along axis direction
  - **base extrusion**: Sketch + Extrude with inferred profile boundary
- execute generated code when `build123d` is available
- export `STEP` and preview `STL`
- attach build metadata such as volume and extents

**Angled feature script generation:**

- When a through-hole or blind hole has non-aligned axes (stored in feature as `axis_origin` and `axis_direction`), the script generator creates a dedicated `REVOLVE_PLANE` (pose-aware sketch plane) perpendicular to that axis
- The sketch is located at the axis origin with local X and Y spanned by radial directions, preserving hole entry geometry
- This ensures angled holes drill in the correct direction regardless of part orientation

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
