# ViminCADConverter

**ViminCADConverter** is a **Python toolkit and optional web UI** for turning **triangle meshes** (STL/OBJ/PLY) or **dense point clouds** (`.xyz`, `.pts`, `.csv`, `.npy`, and point-only `.ply` fallbacks) into a **small parametric CAD program** (currently **build123d**), with optional **STEP** and preview **STL** export when `build123d` is installed.

The installable Python package and CLI entry points keep the name **`mesh2cad`** (import `mesh2cad`, commands `mesh2cad`, `mesh2cad-api`, `mesh2cad-ui`).

Scope today:

- **Prismatic route**: paired parallel planes → base extrusion profile (convex or simple concave), optional **through-holes** from cylinder fits.
- **Rotational route**: when the global shape looks like a solid of revolution and a strong **cylinder** primitive exists, emit a **pose-aware revolve** script (`REVOLVE_PLANE` + `Axis(ORIGIN, AXIS_DIR)` from the inferred axis).

## Roadmap (depth and breadth)

We treat **deeper current routes** (cleaner sketches, holes, frames, validation) and **new mechanical workflows** (e.g. additional part classes) as parallel goals, not either/or. Every meaningful change should land with **tests** (unit/smoke) and, where applicable, **benchmark catalog** updates in `benchmarks/cases.json` so CI stays honest.

## Install

```bash
pip install -e .
# CLI + numpy stack only

pip install -e ".[dev]"        # pytest
pip install -e ".[api]"       # FastAPI + uvicorn + pydantic
pip install -e ".[full]"      # adds build123d, open3d, gradio, …
pip install -e ".[queue]"     # optional: redis + rq for future durable workers
```

Requires **Python ≥ 3.11**.

## CLI

```bash
mesh2cad input.stl --output-dir ./out
mesh2cad input.stl --no-build --sample-count 8000
mesh2cad input.stl --no-auto-tune   # use exact requested sample count
mesh2cad cloud.xyz --no-build --icp-iterations 15   # point cloud input; validation ICP knobs
```

## HTTP API & UI

```bash
mesh2cad-api   # http://127.0.0.1:8000
mesh2cad-ui    # minimal Gradio panel (http://127.0.0.1:7860) if gradio is installed
```

- `POST /process` — synchronous JSON body (`ProcessMeshRequest`: `input_path`, `build`, `sample_count`, `simplify_target_faces`, `auto_tune_sampling`, `align_surface_metrics`, `icp_iterations`, `icp_seed`, …).
- `POST /process/submit` — queue job, poll `GET /process/jobs/{job_id}`.
- `POST /process/jobs/{job_id}/cancel` — cancel queued work or request termination of a running worker (see env vars below).

Browser UI: setup admin user, sign in, upload mesh, download report/script/STEP, see **structured failure** blocks when jobs fail.

## Environment

| Variable | Purpose |
|----------|---------|
| `MESH2CAD_STATE_DIR` | SQLite DB + uploads + job dirs (tests set a temp dir automatically). |
| `MESH2CAD_JOB_TIMEOUT_SEC` | Worker subprocess wall clock (default `900`). |
| `MESH2CAD_MAX_UPLOAD_MB` | UI upload cap. |
| `MESH2CAD_SECURE_COOKIES` | Set `true` behind HTTPS. |

## Benchmarks & north star

- Catalog: `benchmarks/cases.json` (synthetic meshes, no large binaries). Runner: `mesh2cad.benchmarks.runner`.
- Product intent and acceptance focus: `docs/NORTH_STAR.md`.

## Development

```bash
pytest -q
```

CI (`.github/workflows/ci.yml`) runs the main suite on Python **3.11** and **3.12** with `pip install -e ".[dev,api]"`, and a separate job installs **build123d** to exercise validation tests that require it.

## Publish to GitHub (you run these locally)

This environment cannot sign in to your GitHub account. After creating an empty repository named **`ViminCADConverter`** on GitHub (same spelling as the title you want):

```bash
cd /path/to/CADConverterVimin   # or wherever you keep this tree
git remote add origin https://github.com/YOUR_USERNAME/ViminCADConverter.git
git branch -M main
git push -u origin main
```

If the repo is not initialized yet:

```bash
git init
git add .
git commit -m "Initial commit: ViminCADConverter"
git remote add origin https://github.com/YOUR_USERNAME/ViminCADConverter.git
git branch -M main
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub user or organization. If you use SSH, use `git@github.com:YOUR_USERNAME/ViminCADConverter.git` instead.
