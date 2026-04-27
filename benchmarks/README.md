# ViminCADConverter benchmarks

`cases.json` lists lightweight regression scenarios. Each case is synthetic geometry generated at test time (no large binaries in git). The runner lives in `mesh2cad.benchmarks.runner` and is exercised by `tests/test_benchmarks.py`. A case may set **`build_export`: true** to write STEP/STL under the temp dir (requires **build123d**; the parametrized test skips otherwise). **`expect_warning_substr`** matches any merged pipeline warning substring after that run.

**Generators** (see `runner._make_mesh` / `_make_input_mesh_path`):

- **`box`** — `extents` `[sx, sy, sz]`.
- **`cylinder`** — `radius`, `height`, optional `sections`.
- **`capsule`** — curved stock proxy: `height`, `radius`, optional `count_a` / `count_b` (passed to `trimesh.creation.capsule` as `count`).
- **`icosphere`** — dense sphere mesh; routing depends on `subdivisions` / sampling (catalog may expect **`revolve_simple`** or **`none`**; see `cases.json`).
- **`point_cloud_box`** — surface samples from a box to `.xyz`; optional **`point_noise_std`** and **`noise_seed`** for reproducible Gaussian jitter on points.

Environment variables:

- `MESH2CAD_JOB_TIMEOUT_SEC` — worker subprocess wall clock (default 900).
- `MESH2CAD_STATE_DIR` — SQLite and job artifacts root (tests set this automatically).
