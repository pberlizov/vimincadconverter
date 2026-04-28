# ViminCADConverter

**ViminCADConverter** is a **Python toolkit and optional web UI** for turning **triangle meshes** (STL/OBJ/PLY) or **dense point clouds** (`.xyz`, `.pts`, `.csv`, `.npy`, and point-only `.ply` fallbacks) into a **small parametric CAD program** (currently **build123d**), with optional **STEP** and preview **STL** export when `build123d` is installed.

The installable Python package and CLI entry points keep the name **`mesh2cad`** (import `mesh2cad`, commands `mesh2cad`, `mesh2cad-api`, `mesh2cad-ui`).

Scope today:

- **Prismatic route**: paired parallel planes → base extrusion profile (convex or simple concave), with support for:
  - through-holes inferred from cylinder fits, including angled/non-parallel axes when the hole axis intersects the stock faces
  - countersinks (cone primitives) paired with through-holes, including angled countersinks
  - blind holes, including angled/non-parallel blind holes with explicit axis specification
- **Rotational route**: when the global shape looks like a solid of revolution and a strong **cylinder** primitive exists, emit a **pose-aware revolve** script (`REVOLVE_PLANE` + `Axis(ORIGIN, AXIS_DIR)` from the inferred axis).
- **Build123d script-first synthesis**: generated Python code can be executed later when `build123d` is installed to produce `STEP` and preview `STL` exports.

Current CAD feature support:

- `BaseExtrudeFeature` recovery from paired parallel stock faces and an extrusion profile.
- `ThroughHoleFeature` inference from cylinder primitives, including angled/non-parallel hole axes when the cylinder primitive axis crosses the inferred stock faces.
- `CounterSinkHoleFeature` support for countersink cones paired with through-holes, including angled countersinks aligned to angled hole axes.
- `BlindHoleFeature` inference including support for angled/non-parallel axes.
- `RevolveSolidFeature` for simple rotational parts when a strong cylinder primitive dominates.
- generated `build123d` script output, with optional execution to produce `STEP` and preview `STL`.

Current limitations:

- boss/pocket inference is not yet robust for general noisy inputs.
- unsupported: organic freeform geometry, assemblies, sheet-metal-specific reasoning, and advanced feature-tree semantics.

## Roadmap (depth and breadth)

We treat **deeper current routes** (cleaner sketches, holes, frames, validation) and **new mechanical workflows** (e.g. additional part classes) as parallel goals, not either/or. Every meaningful change should land with **tests** (unit/smoke) and, where applicable, **benchmark catalog** updates in `benchmarks/cases.json` so CI stays honest.

## Install

From a clone of this repository:

```bash
pip install -e .
# CLI + numpy stack only

pip install -e ".[dev]"        # pytest
pip install -e ".[api]"       # FastAPI + uvicorn + pydantic
pip install -e ".[full]"      # adds build123d, open3d, gradio, …
pip install -e ".[queue]"     # optional: redis + rq for Redis-backed job workers
pip install -e ".[open3d]"    # optional: Open3d for MESH2CAD_USE_OPEN3D_METRICS (also in [full])
pip install -e ".[cad]"       # optional: build123d only (Dockerfile.full / in-container STEP export)
```

Requires **Python ≥ 3.11**.

## Usage

### Command-line (`mesh2cad`)

Typical flows:

```bash
# Mesh → report + build123d script + optional STEP/STL when build123d is installed
mesh2cad part.stl --output-dir ./out

# Script and metrics only (no CAD execution)
mesh2cad part.stl --no-build --sample-count 8000

# Fixed sample count (disable automatic sample tuning)
mesh2cad part.stl --no-auto-tune

# Point cloud input; optional ICP tuning for validation
mesh2cad cloud.xyz --no-build --icp-iterations 15
```

Outputs under `--output-dir` include the structured report and generated Python; with **`build123d`** installed and build enabled, you also get STEP/preview STL when the pipeline succeeds.

### HTTP API (`mesh2cad-api`)

```bash
export MESH2CAD_STATE_DIR=/var/lib/mesh2cad   # required for uploads and job storage
mesh2cad-api   # default http://127.0.0.1:8000 — use MESH2CAD_BIND_HOST=0.0.0.0 in containers
```

- **Interactive docs:** `http://<host>:8000/docs` (OpenAPI).
- **Health:** `GET /health` (process up), `GET /ready` (SQLite + state dir writable; with **`MESH2CAD_JOB_BACKEND=rq`** also checks **Redis**).

**Synchronous** upload + process (`multipart/form-data`, field `file`):

```bash
curl -sS -X POST "http://127.0.0.1:8000/v1/process" \
  -H "X-API-Key: YOUR_KEY" \
  -F "file=@./part.stl" \
  -F "build=true" \
  -F "include_script=true"
```

Omit **`X-API-Key`** when **`MESH2CAD_API_KEYS`** is not configured (local development only).

**Asynchronous** job (same form fields as `/v1/process`; poll `GET /v1/jobs/{id}` or subscribe to `GET /v1/jobs/{id}/events`):

```bash
curl -sS -X POST "http://127.0.0.1:8000/v1/jobs" \
  -H "X-API-Key: YOUR_KEY" \
  -H "Idempotency-Key: unique-string" \
  -F "file=@./part.stl"
```

When **`MESH2CAD_API_KEYS`** is set, send **`X-API-Key`** or **`Authorization: Bearer <key>`** on every `/v1` call.

**Legacy routes** (`POST /process`, `POST /process/submit`, job polling under `/process/jobs/...`) remain for older integrations; new work should use **`/v1`**.

### Web UI (`mesh2cad-ui`)

```bash
mesh2cad-ui    # default http://127.0.0.1:7860 — Gradio: path or upload, JSON + downloads
```

Uses **`MESH2CAD_STATE_DIR`** (or **`$TMPDIR`**) for temp uploads and job files. First-run browser UI may prompt for an admin user (see app logs for setup URLs).

### Docker (single host)

```bash
cp deploy/env.example .env    # optional; edit MESH2CAD_* and ports
docker compose up --build     # API on port 8000 (MESH2CAD_HOST_PORT)
```

**Redis + background workers** (recommended when jobs are long or you want the API process to stay responsive):

```bash
docker compose -f docker-compose.yml -f docker-compose.queue.yml up -d --build
```

Details: **[docs/deploy-docker.md](docs/deploy-docker.md)**.

### Kubernetes

Production-oriented bundle (in-cluster Redis, **one Pod** with API + `mesh2cad-rq-worker`, **ReadWriteOnce** PVC):

```bash
kubectl apply -k deploy/k8s
```

Edit **`deploy/k8s/deployment-api.yaml`** image references before apply. Thread-only variant and Ingress template: **`deploy/k8s/README.md`**.

## Deploying for users today

The project is **deployable today** as a **single-tenant** service: one persistent **`MESH2CAD_STATE_DIR`**, one coordinated API + job fleet, and no hard dependency on Postgres or S3. That matches internal tools, per-customer VMs, or one namespace per customer.

| You should have | Why |
|-----------------|-----|
| **Persistent disk** for `MESH2CAD_STATE_DIR` | SQLite, uploads, and job artifacts live here. |
| **TLS** in front of the app (reverse proxy or Ingress) | Encrypt traffic; set **`MESH2CAD_SECURE_COOKIES=true`** for the browser UI. |
| **`MESH2CAD_API_KEYS`** on any untrusted network | `/v1` is otherwise open. |
| **Redis + RQ** for production-ish load | `docker-compose.queue.yml` or **`kubectl apply -k deploy/k8s`** so long runs do not block Uvicorn; see **[docs/operations.md](docs/operations.md)**. |
| **Backups + retention** | `scripts/backup-mesh2cad-state.sh` (host) or `kubectl exec` + `tar` (see operations doc); schedule **`mesh2cad-purge-jobs`**. |
| **Observability (optional)** | **`MESH2CAD_LOG_JSON`**, **`MESH2CAD_LOG_LEVEL`**; **`MESH2CAD_METRICS_ENABLED`** for Prometheus (protect **`/metrics`** at the network edge). |

**Prebuilt images:** CI can publish **`ghcr.io/<owner>/<repo>:latest`** (API + queue client) and **`:cad`** (includes **build123d** for in-container STEP export). Pull and point your compose or Kubernetes manifests at those tags.

**Optional distribution:** publish the **`mesh2cad`** package to PyPI (or a private index) so users can `pip install "mesh2cad[api]"` without cloning; you still need a process manager or container for long-running **`mesh2cad-api`**.

**Not required for “today” but needed for multi-tenant SaaS scale-out:** shared Postgres for metadata, object storage / pre-signed downloads for artifacts, and multiple stateless API replicas without SQLite contention — see **[docs/scale-out-roadmap.md](docs/scale-out-roadmap.md)**.

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
| `MESH2CAD_RATE_LIMIT_PER_MINUTE` | Per-client-IP cap on `POST /v1/process`, `POST /v1/jobs`, `POST /process` (default `120`). |
| `MESH2CAD_RATE_LIMIT_BACKEND` | Set **`redis`** with **`MESH2CAD_REDIS_URL`** for shared rate limits across API replicas. |
| `MESH2CAD_RATE_LIMIT_REDIS_PREFIX` | Redis key prefix for rate counters (default `mesh2cad:rl`). |
| `MESH2CAD_MAX_REQUEST_MB` | Max `Content-Length` for POST/PUT/PATCH (default `256` MiB). |
| `MESH2CAD_MAX_REQUEST_BYTES` | Optional exact byte cap (overrides MB when set). |
| `MESH2CAD_JOB_WORKERS` | Thread-pool size for async jobs when **`MESH2CAD_JOB_BACKEND=thread`** (default `2`). |
| `MESH2CAD_JOB_BACKEND` | `thread` (default, in-process pool) or **`rq`** with **`MESH2CAD_REDIS_URL`** for Redis-backed jobs. |
| `MESH2CAD_REDIS_URL` | Redis URL when using **`rq`** (e.g. `redis://redis:6379/0`). |
| `MESH2CAD_RQ_QUEUE` | RQ queue name (default `mesh2cad`). |
| `MESH2CAD_RQ_WORKER_NAME` | Optional RQ worker display name (default `mesh2cad-1`). |
| `MESH2CAD_BIND_HOST` | Uvicorn bind address for **`mesh2cad-api`** (default `127.0.0.1`; use `0.0.0.0` in containers). |
| `MESH2CAD_BIND_PORT` | Uvicorn port (default `8000`). |
| `MESH2CAD_USE_OPEN3D_METRICS` | When `true`/`1` and `open3d` is installed, validation uses Open3D raycasting for point-to-mesh distances (falls back to trimesh otherwise). |
| `MESH2CAD_USE_OPEN3D_CLOUD` | When `true`/`1` and `open3d` is installed, large point clouds use Open3D for **normal estimation** (see `MESH2CAD_OPEN3D_CLOUD_MIN_POINTS`). |
| `MESH2CAD_OPEN3D_CLOUD_MIN_POINTS` | Minimum point count to switch normal estimation to Open3D (default `50000`). |
| `MESH2CAD_JOB_RETENTION_DAYS` | Default for **`mesh2cad-purge-jobs --days`** (see below). |
| `MESH2CAD_WEBHOOK_ALLOW_HTTP` | Set `true` to allow `http://` webhook URLs (dev only). |

### Job retention

Terminal jobs (`completed` / `failed` / `cancelled`) older than **N** days (by `updated_at`) can be removed from SQLite and disk:

```bash
mesh2cad-purge-jobs --days 30
```

Run on a schedule (e.g. weekly cron) so `MESH2CAD_STATE_DIR` does not grow without bound.

### Single replica vs horizontal scale

- **Today:** SQLite, on-disk job artifacts, in-process rate limits, and (by default) a **thread-pool** job runner are **single-host assumptions**. Run **one API replica** per `MESH2CAD_STATE_DIR` unless you understand SQLite concurrency limits, or use **sticky sessions** and accept that rate limits are per-process.
- **Horizontal job workers:** set **`MESH2CAD_JOB_BACKEND=rq`** and **`MESH2CAD_REDIS_URL`**, then run **`mesh2cad-rq-worker`** (see **`docker-compose.queue.yml`**). On Kubernetes with a **ReadWriteOnce** PVC, run the API and worker in one Pod (`kubectl apply -k deploy/k8s`). Workers still share **`MESH2CAD_STATE_DIR`** and SQLite; WAL mode helps but you should keep concurrent writers low. See **[docs/operations.md](docs/operations.md)** and **`deploy/k8s/README.md`**.
- **Long-term scale:** shared object storage for artifacts and a non-SQLite job store remain a product direction beyond RQ.

### Docker and Kubernetes (reference)

Images: **`Dockerfile`** (API + queue), **`Dockerfile.full`** (**`[cad]`** / build123d). Compose: **`docker-compose.yml`**, **`docker-compose.queue.yml`**. Health checks use **`GET /ready`**. Pushes to **`main`** / **`master`** can publish **`ghcr.io/<owner>/<repo>:latest`**, **`:cad`**, and SHA-tagged variants (**Publish container images** workflow). Full checklist: **[docs/deploy-docker.md](docs/deploy-docker.md)**.

## Security and privacy

- Processing is **local** by default; this repo does not embed calls to paid third-party “AI mesh” APIs.
- **Do not commit** real API keys, tokens, or production passwords (`.env` is gitignored). Automated tests use **dummy** credentials only; change defaults for real deployments.
- If a secret is ever pasted into chat, a ticket, or a commit, **revoke and rotate** it immediately—assume it is compromised.

## Benchmarks & north star

- Catalog: `benchmarks/cases.json` (synthetic meshes, no large binaries). Runner: `mesh2cad.benchmarks.runner`. Cases may set **`build_export`: true** to run STEP/STL export (needs optional **build123d**); optional **`expect_warning_substr`** checks merged pipeline warnings (for example validation surface strings). **`expect_route_any_of`** and **`min_feature_kind_counts_by_route`** allow routing-sensitive cases (for example capsule) without brittle single-route assertions. The **`build123d_two_hole_plate`** generator materializes a preview STL via **build123d** (skipped in `pytest` when build123d is not installed); CI runs those cases in the **test-with-build123d** workflow job.
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
