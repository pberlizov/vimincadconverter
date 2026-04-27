# ViminCADConverter benchmarks

`cases.json` lists lightweight regression scenarios. Each case is synthetic geometry generated at test time (no large binaries in git). The runner lives in `mesh2cad.benchmarks.runner` and is exercised by `tests/test_benchmarks.py`.

Environment variables:

- `MESH2CAD_JOB_TIMEOUT_SEC` — worker subprocess wall clock (default 900).
- `MESH2CAD_STATE_DIR` — SQLite and job artifacts root (tests set this automatically).
