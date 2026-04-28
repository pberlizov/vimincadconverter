# Scale-out roadmap

This document orders the remaining work to run **multiple API replicas**, **durable horizontal workers**, and **cloud-native storage** without the current single-host SQLite assumptions.

## Done today

- **Docker** images (`:latest`, `:cad`) and **GHCR** publish workflow.
- **Redis + RQ** for async mesh jobs with **shared `MESH2CAD_STATE_DIR`** (WAL SQLite, cancel semantics preserved).
- **`GET /ready`** pings **Redis** when **`MESH2CAD_JOB_BACKEND=rq`**.
- **Kubernetes (`deploy/k8s/`)** — Kustomize stack with in-cluster Redis, **combined API + RQ worker Pod** (RWO-safe), optional Ingress example, and a thread-only Deployment variant.
- **Redis-backed rate limits** (`MESH2CAD_RATE_LIMIT_BACKEND=redis` + `MESH2CAD_REDIS_URL`) for consistent POST throttling across replicas.
- **Optional Open3D** for large point-cloud **normal estimation** (`MESH2CAD_USE_OPEN3D_CLOUD`).

## Phase 1 — Operate multiple replicas safely (still SQLite)

1. **Single writer for SQLite** — either one API pod with many **RQ workers**, or multiple API pods each with **isolated** state volumes (no shared DB).
2. **Ingress + TLS** — terminate HTTPS at the load balancer; set **`MESH2CAD_SECURE_COOKIES`**.
3. **Backups** — automate **`scripts/backup-mesh2cad-state.sh`** (see **`docs/operations.md`**).

## Phase 2 — Shared metadata (Postgres)

1. Add a **repository abstraction** for jobs, users, sessions, and idempotency keys (today in `mesh2cad/ui/db.py`).
2. Introduce **`DATABASE_URL`** (Postgres) behind the same API; migrate schema with explicit migration scripts.
3. Keep **blob paths** on disk or move to object storage (phase 3) while Postgres stores paths and status only.

## Phase 3 — Object storage

1. Pluggable **artifact store** (local disk vs S3-compatible) for uploads, `report.json`, STEP/STL outputs.
2. **Pre-signed URLs** for downloads instead of streaming from local disk in multi-replica setups.
3. Optional **CDN** in front of static/preview assets.

## Phase 4 — Hardening

1. **Distributed tracing** (OpenTelemetry) and structured correlation IDs (request id already exists).
2. **Secrets** from KMS / sealed secrets in Kubernetes.
3. **Autoscaling** workers on queue depth (KEDA + Redis) once metadata is off single-writer SQLite.

Use **`deploy/k8s/`** as a starting point for a single-replica API + PVC; extend with Helm values when Phase 2+ land.
