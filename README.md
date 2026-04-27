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
mesh2cad-ui    # Gradio panel (http://127.0.0.1:7860): path or file upload, JSON + downloads (report / script / STEP / preview STL); temp work under $TMPDIR or MESH2CAD_STATE_DIR
```

- **`/v1` (recommended for integrations)** — OpenAPI `/docs` lists full schemas. Summary:
  - `GET /health`, `GET /ready` — unauthenticated probes (`ready` checks SQLite + state dir).
  - `POST /v1/process` — synchronous run; **JSON** (`ProcessMeshBodyV1`: `input_path`, `build`, `include_script`, `tolerances`, `icp_hybrid_hull_weight`, …) or **`multipart/form-data`** with field `file` (STL/OBJ/PLY/xyz/pts/csv/npy) plus optional form fields mirroring the JSON keys.
  - `POST /v1/jobs` — async job; same JSON or multipart; optional header **`Idempotency-Key`**; optional JSON field **`webhook_url`** (terminal-state POST; HMAC header **`X-Mesh2cad-Signature`** when `MESH2CAD_WEBHOOK_SECRET` is set).
  - `GET /v1/jobs/{job_id}` — status + payload.
  - `GET /v1/jobs/{job_id}/artifacts/{name}` — download `report`, `script`, `step`, `preview`, or `input` (authenticated when API keys are configured).
  - `GET /v1/jobs/{job_id}/events` — SSE stream of `{ "status": ... }` until terminal.
  - `POST /v1/jobs/{job_id}/cancel` · `POST /v1/jobs/{job_id}/retry` — same semantics as legacy routes below.
  - When **`MESH2CAD_API_KEYS`** is set (comma-separated), v1 routes require **`X-API-Key`** or **`Authorization: Bearer <key>`**. If unset, v1 remains open (development only).
  - **`MESH2CAD_CORS_ORIGINS`** — comma-separated list to enable CORS for browser clients.
- **Legacy (unchanged)** — `POST /process` (sync JSON, extended with `include_script`, `tolerances`, `icp_hybrid_hull_weight`), `POST /process/submit` (optional `webhook_url`), `GET /process/jobs/{job_id}`, cancel/retry — no API key layer.

Browser UI: setup admin user, sign in, upload mesh, download report/script/STEP, see **structured failure** blocks when jobs fail.

## Security and privacy

- Processing is **local** by default; this repo does not embed calls to paid third-party “AI mesh” APIs.
- **Do not commit** real API keys, tokens, or production passwords (`.env` is gitignored). Automated tests use **dummy** credentials only; change defaults for real deployments.
- If a secret is ever pasted into chat, a ticket, or a commit, **revoke and rotate** it immediately—assume it is compromised.

## Environment

| Variable | Purpose |
|----------|---------|
| `MESH2CAD_STATE_DIR` | SQLite DB + uploads + job dirs (tests set a temp dir automatically). |
| `MESH2CAD_JOB_TIMEOUT_SEC` | Worker subprocess wall clock (default `900`). |
| `MESH2CAD_MAX_UPLOAD_MB` | UI and `/v1` upload cap. |
| `MESH2CAD_SECURE_COOKIES` | Set `true` behind HTTPS. |
| `MESH2CAD_API_KEYS` | Comma-separated keys required for `/v1/*` when set. |
| `MESH2CAD_WEBHOOK_SECRET` | Optional HMAC key for job webhooks (`sha256=` prefix on `X-Mesh2cad-Signature`). |
| `MESH2CAD_CORS_ORIGINS` | Comma-separated allowed origins for CORS. |
| `MESH2CAD_LOG_LEVEL` | Python log level (`INFO`, `DEBUG`, …). |
| `MESH2CAD_LOG_JSON` | Set `true` for JSON lines on stderr (ingestion-friendly). |
| `MESH2CAD_METRICS_ENABLED` | Set `true` to expose Prometheus text at **`GET /metrics`** (no API key; protect with network policy). |
| `MESH2CAD_RATE_LIMIT_PER_MINUTE` | Per-client-IP cap on `POST /v1/process`, `POST /v1/jobs`, `POST /process` (default `120`; in-memory, **single replica**). |
| `MESH2CAD_MAX_REQUEST_MB` | Max `Content-Length` for POST/PUT/PATCH (default `256` MiB). |
| `MESH2CAD_MAX_REQUEST_BYTES` | Optional exact byte cap (overrides MB when set). |
| `MESH2CAD_JOB_WORKERS` | Thread-pool size for async jobs (default `2`). |
| `MESH2CAD_JOB_RETENTION_DAYS` | Default for **`mesh2cad-purge-jobs --days`** (see below). |
| `MESH2CAD_WEBHOOK_ALLOW_HTTP` | Set `true` to allow `http://` webhook URLs (dev only). |

### Job retention

Terminal jobs (`completed` / `failed` / `cancelled`) older than **N** days (by `updated_at`) can be removed from SQLite and disk:

```bash
mesh2cad-purge-jobs --days 30
```

Run on a schedule (e.g. weekly cron) so `MESH2CAD_STATE_DIR` does not grow without bound.

### Single replica vs horizontal scale

- **Today:** SQLite, on-disk job artifacts, in-process rate limits, and the thread-pool job runner are **single-host assumptions**. Run **one API/worker replica** per `MESH2CAD_STATE_DIR`, or use **sticky sessions** and accept that rate limits are per-process.
- **Horizontal scale:** use a **shared queue + object storage** (the optional **`[queue]`** extra points at Redis/RQ) and move job metadata off SQLite, or partition one writer for the DB.

## Benchmarks & north star

- Catalog: `benchmarks/cases.json` (synthetic meshes, no large binaries). Runner: `mesh2cad.benchmarks.runner`. Cases may set **`build_export`: true** to run STEP/STL export (needs optional **build123d**); optional **`expect_warning_substr`** checks merged pipeline warnings (for example validation surface strings).
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
