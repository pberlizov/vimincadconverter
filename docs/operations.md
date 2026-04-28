# Operations

## Backups

- **What to back up:** the entire directory set by **`MESH2CAD_STATE_DIR`** (SQLite file `mesh2cad.sqlite3`, `uploads/`, and `jobs/`).
- **How often:** at least daily for busy instances; align retention with **`mesh2cad-purge-jobs`** (see README).
- **Script:** from the repo root, `bash scripts/backup-mesh2cad-state.sh /path/to/backup.tar.gz` (requires `MESH2CAD_STATE_DIR` in the environment).
- **Restore:** stop the API and workers, restore the directory onto a clean host with the same path (or update `MESH2CAD_STATE_DIR`), then start services. Verify **`GET /ready`** and spot-check a known job id in SQLite if you need consistency guarantees.

## Redis + RQ workers

- **When to use:** offload long jobs from the API process so Uvicorn stays responsive; scale **worker replicas** horizontally while keeping **one shared `MESH2CAD_STATE_DIR`** on a volume all pods can mount (or use shared NFS/object storage in a future revision).
- **Configuration:** set **`MESH2CAD_JOB_BACKEND=rq`**, **`MESH2CAD_REDIS_URL`** (e.g. `redis://redis:6379/0`), and optionally **`MESH2CAD_RQ_QUEUE`** (default `mesh2cad`). Install **`[queue]`** (included in the default Docker image extras).
- **Run a worker:** **`mesh2cad-rq-worker`** (same image and env as the API, including `MESH2CAD_STATE_DIR`).
- **Compose:** `docker compose -f docker-compose.yml -f docker-compose.queue.yml up -d` starts Redis, switches the API to RQ mode, and runs one worker. Adjust replicas by duplicating the `rq-worker` service or using an orchestrator.
- **Cancelling jobs:** queued RQ jobs are removed via **`job.cancel()`**; running jobs still rely on the on-disk **cancel marker** and subprocess termination (same as the in-process thread pool).

## SQLite concurrency

- Connections enable **WAL** and a **busy timeout** so the API and RQ workers can share one database file more safely. You should still avoid dozens of concurrent writers; prefer a modest **`MESH2CAD_JOB_WORKERS`** / worker count.

## Container images (GHCR)

- On pushes to **`main`** / **`master`**, **Publish container images** builds and pushes:
  - **`:latest`** and **`:api-<sha>`** — slim API + queue client (`Dockerfile`).
  - **`:cad`** and **`:cad-<sha>`** — API + queue + **build123d** (`Dockerfile.full`, larger).
- Pull example: `docker pull ghcr.io/<owner>/<repo>:latest` (use your repository’s lowercase path).

## Graceful API shutdown

- On SIGTERM/SIGINT, the FastAPI lifespan hook calls **`shutdown_job_executor()`** so in-flight **thread-pool** jobs are allowed to finish (**`wait=True`**, **`cancel_futures=False`**). RQ jobs are unaffected (they run in worker processes).

## Readiness (`GET /ready`)

- Checks SQLite and the state directory as before.
- When **`MESH2CAD_JOB_BACKEND=rq`** and **`MESH2CAD_REDIS_URL`** are set, **`/ready`** also **`PING`s Redis** so load balancers do not send traffic before the queue is reachable.

## Rate limits across replicas

- Default: in-memory fixed window (**single replica**).
- Set **`MESH2CAD_RATE_LIMIT_BACKEND=redis`** with the same **`MESH2CAD_REDIS_URL`** as RQ (or a dedicated Redis) so **`POST /v1/process`**, **`POST /v1/jobs`**, and legacy **`POST /process`** share a cluster-wide counter. Optional **`MESH2CAD_RATE_LIMIT_REDIS_PREFIX`** (default `mesh2cad:rl`) namespaces keys.

## Large point clouds (Open3D)

- With **`MESH2CAD_USE_OPEN3D_CLOUD=1`** and **`open3d`** installed, normal estimation for point clouds uses Open3D above **`MESH2CAD_OPEN3D_CLOUD_MIN_POINTS`** (default `50000`). Smaller clouds keep the SciPy k-NN path.

## Longer-term scale

- See **[docs/scale-out-roadmap.md](scale-out-roadmap.md)** for Postgres, object storage, and multi-replica API phases.
