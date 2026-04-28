# Docker deployment

## Quick start

From the repository root:

```bash
cp deploy/env.example .env   # optional; edit values
docker compose up --build
```

The API listens on port **8000** by default (`MESH2CAD_HOST_PORT` overrides the host mapping). Health checks call **`GET /ready`**, which verifies SQLite and the state directory (and **Redis** when RQ mode is enabled).

## Production checklist

1. **Persistent volume** for `MESH2CAD_STATE_DIR` (compose named volume or cloud disk).
2. **TLS** at the reverse proxy; set **`MESH2CAD_SECURE_COOKIES=true`** for the UI.
3. **`MESH2CAD_API_KEYS`** for `/v1` in any untrusted network.
4. **Backups:** `scripts/backup-mesh2cad-state.sh` and retention via **`mesh2cad-purge-jobs`** (see **`docs/operations.md`**).
5. **Jobs at scale:** `docker-compose.queue.yml` + Redis, or Kubernetes **`deploy/k8s/`** with one writer to SQLite unless you follow **`docs/scale-out-roadmap.md`**.
6. **Images:** pull **`ghcr.io/<owner>/<repo>:latest`** (API) or **`:cad`** for in-container STEP export; CI publishes on push to default branch.

## Image variants

| File | Installs | Typical tags (GHCR) |
|------|----------|---------------------|
| `Dockerfile` | `.[api,queue]` (default build-arg `PIP_EXTRAS`) | `:latest`, `:api-<sha>` |
| `Dockerfile.full` | `.[api,queue,cad]` (build123d + CAD export) | `:cad`, `:cad-<sha>` |

Override Python extras at build time:

```bash
docker build --build-arg PIP_EXTRAS=api -t mesh2cad:api-only .
```

## Redis + RQ (optional)

To run async jobs out-of-process:

```bash
docker compose -f docker-compose.yml -f docker-compose.queue.yml up -d --build
```

This starts **Redis**, sets the API to **`MESH2CAD_JOB_BACKEND=rq`**, and runs **`mesh2cad-rq-worker`**. All services must share the **`mesh2cad_state`** volume so workers read the same SQLite DB and job directories.

## State directory and scaling

- **`MESH2CAD_STATE_DIR`** (default in the image: `/data/state`) holds the SQLite job database, uploads, and per-job artifacts. Mount a **named volume** or host directory so data survives container restarts.
- **One SQLite database per coordinated fleet.** Multiple API containers on the same DB without a shared queue is still risky; with **RQ**, prefer **one API** (or few) plus **several workers**, all mounting the same state volume, and keep total write concurrency modest.
- **Multiple independent deployments** can each use their own `MESH2CAD_STATE_DIR` and scale workers with RQ.

## Bind address

Inside the container the server binds to **`MESH2CAD_BIND_HOST`** (default `0.0.0.0`) and **`MESH2CAD_BIND_PORT`** (default `8000`). The image runs as a **non-root** user (`mesh2cad`, uid 1000).

## Optional Open3D metrics

Validation can use Open3D’s raycasting scene for point-to-mesh distances when **`MESH2CAD_USE_OPEN3D_METRICS=1`** and `open3d` is installed (e.g. `pip install -e ".[full]"` or an image layer that adds the `open3d` dependency). If Open3D is missing or the path fails, the code falls back to **trimesh** proximity as before.

## Further reading

- **[docs/operations.md](operations.md)** — backups, GHCR tags, graceful shutdown, RQ operations, Redis rate limits.
- **[docs/scale-out-roadmap.md](scale-out-roadmap.md)** — Postgres, object storage, multi-replica phases.
- **`deploy/k8s/`** — starter Kubernetes Deployment + PVC + Service.
