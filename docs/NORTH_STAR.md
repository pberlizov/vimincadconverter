# North star: what ViminCADConverter optimizes for first

## Target geometry

The pipeline is intentionally scoped to **mechanical prismatic parts with planar stock and through-holes**, plus a first **rotational** path when the global bounding box and dominant **cylinder** primitive agree.

Out of scope for this phase: freeform organic surfaces, sheet-metal bends, assemblies, and constraint-driven parametric editing in-host.

## Definition of done (per release)

1. **Correct route**: `reconstruction_plan.route` matches the intended solver (`prismatic_extrude` vs `revolve_simple`).
2. **Script validity**: generated `build123d` code runs when optional `build123d` is installed.
3. **Regression**: catalog cases in `benchmarks/cases.json` pass in CI.
4. **Observability**: failures expose `payload.failure` with stage, type, message, and hints (worker, timeout, cancel).

## Metrics

Use `validation_report` (volume / bbox / optional surface RMS when a preview STL exists) as the primary numerical comparison against the source mesh. Extrude output uses inferred `sketch_plane` in `Plane(origin=…, x_dir=…, z_dir=…)`; revolve output uses `Axis(ORIGIN, AXIS_DIR)` and a matching sketch plane (see `reconstruction_plan.notes` when present).

## Backlog (near-term)

- Tighter **ICP / preview** alignment when the source proxy is a convex hull from dense points (today ICP still targets the hull mesh).
- **Redis/RQ** (optional `queue` extra): wire job submission to a durable worker while preserving `payload.failure` semantics and cancel markers.
- Richer **benchmark catalog** (curved stock, noisy samples, intentional routing failures) and optional Open3D-accelerated proximity where available.
- **Gradio** polish (upload to temp dir, download script bundle) beyond the minimal `mesh2cad-ui` path entry.
