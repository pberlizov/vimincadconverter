# Failure Modes

This document lists the main ways the current pipeline can fail or degrade, and what those failures usually look like.

## Primitive-level failures

### Plane over-coverage

Symptom:

- too many points get absorbed by plane hypotheses
- residual cloud for cylinder fitting becomes too small

Current mitigation:

- cylinder fitting falls back to the full cloud when residual support is too small

### False cylinder hypotheses on noisy triangulated meshes

Symptom:

- many axis-aligned cylinder candidates appear on damaged vertical walls
- through-hole count inflates

Current mitigation:

- residual-cloud preference
- sidewall clustering before candidate-center inference
- stricter angular support coverage
- crowded-candidate filtering in through-hole inference

## Feature-level failures

### Missing holes under aggressive artifacts

Symptom:

- base extrusion recovers
- through-hole inference returns none

Known triggers:

- strong quantization
- face dropout
- weak or fragmented cylindrical support

Current policy:

- treat some of these cases as degraded-but-structured rather than total failure

### Angled through-hole inference failures

Symptom:

- a cylinder primitive is present, but the inferred hole feature is not recognized as through-hole because the axis does not sufficiently intersect the expected top/bottom faces or the profile fit is marginal.

Known triggers:

- angled/non-parallel hole axes with noisy mesh regions around face intersections
- ambiguous entry/exit points at the stock boundary

Current policy:

- preserve base extrusion recovery where possible and emit warnings rather than failing the entire pipeline

### Extra holes on scan-like meshes

Symptom:

- more hole features than the real part likely contains

Known triggers:

- noisy triangulated wall fragments
- unstable outer profile geometry

Current status:

- improved, but not eliminated

## Route-level failures

### No base extrusion inferred

Symptom:

- feature list is empty
- warnings include base-extrusion failure

Known triggers:

- weak paired planar stock
- broken or heavily missing mesh regions
- geometry outside the targeted prismatic/rotational scope

### Wrong route choice

Symptom:

- route notes or downstream script shape do not match intended part class

Current mitigation:

- route/plan observability via reconstruction planning data
- benchmark expansion is still needed here

## Execution-level failures

### Generated script does not build

Symptom:

- synthesis succeeds at script generation but build/export fails

Current mitigation:

- preserve warnings and errors in the result payload
- keep `build=False` path usable for inference-only workflows

### Missing optional dependencies

Examples:

- `build123d` missing
- `rtree` missing

Current mitigation:

- graceful degradation where possible
- fallback paths in validation when proximity dependencies are absent

## Operational failures

### Long-running jobs

Symptom:

- UI/API job remains in `processing`

Current mitigation:

- subprocess-backed execution
- async status endpoints
- longer polling windows in tests

Not yet present:

- durable queue
- retry policy
- stronger cancellation/supervision guarantees

## How to read failures today

Current observability surfaces:

- `warnings` in pipeline results
- `validation_report`
- job artifact payloads
- UI job detail page

The project still needs a more explicit invalid-solid warning path and a broader failure benchmark catalog.
