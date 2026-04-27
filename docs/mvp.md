# MVP Definition

## Goal

The current MVP is not "convert any 3D object into CAD." It is:

> Recover a usable lightweight CAD description for simple mechanical parts from messy mesh-like input, with local execution and script-first output.

## Supported success shape

The MVP is successful when it can do all of the following on representative prismatic parts:

- identify a prismatic route from paired planar stock
- recover a base extrusion profile
- recover at least some through-holes from cylinder evidence
- emit valid `build123d` code
- export `STEP` and preview `STL` when `build123d` is installed
- report validation metrics and structured warnings

## Inputs

Current practical inputs:

- triangle meshes: `STL`, `OBJ`, `PLY`
- dense point-oriented fallbacks described in the README and geometry input modules

The best-covered path today is still triangulated mesh input.

## Outputs

Current outputs:

- JSON-friendly pipeline result
- generated `build123d` script
- optional `STEP`
- optional preview `STL`
- detection and validation reports
- job artifacts exposed through the UI/API

## Supported part classes

Primary MVP class:

- prismatic plates, brackets, and stock-like parts with through-holes

Secondary MVP class:

- simple rotational solids when a strong cylinder primitive dominates and the revolve route is chosen

## Acceptance bar

The MVP bar is met when:

- benchmark and smoke fixtures pass
- generated script execution is valid where `build123d` exists
- validation metrics are exposed
- failures are observable through structured warnings or payload failure objects

## Explicitly not in MVP

- organic freeform reconstruction
- assemblies
- sheet-metal bend reasoning
- robust boss/pocket inference across real noisy meshes
- feature-tree parity with commercial reverse-engineering tools
- exact recovery of every hole candidate on damaged triangulated inputs
- durable distributed queue infrastructure

## What "good enough" means right now

For some artifact-heavy cases, the MVP currently accepts degraded-but-structured behavior:

- base extrusion recovered
- hole recovery may partially fail
- warnings remain visible

That is still useful and testable, and it is explicitly represented in the artifact-matrix tests.
