# ViminCADConverter benchmarks

`cases.json` lists lightweight regression scenarios. Each case is synthetic geometry generated at test time (no large binaries in git). The runner lives in `mesh2cad.benchmarks.runner` and is exercised by `tests/test_benchmarks.py`. A case may set **`build_export`: true** to write STEP/STL under the temp dir (requires **build123d**; the parametrized test skips otherwise). **`expect_warning_substr`** matches any merged pipeline warning substring after that run.

Environment variables:

- `MESH2CAD_JOB_TIMEOUT_SEC` — worker subprocess wall clock (default 900).
- `MESH2CAD_STATE_DIR` — SQLite and job artifacts root (tests set this automatically).
