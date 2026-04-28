# Kubernetes (starting point)

These manifests target a **single API replica** with a **ReadWriteOnce** PVC for `MESH2CAD_STATE_DIR` — the same layout as `docker compose`.

## Before you apply

1. Copy **`../env.example`** to a local env file or set variables in the Deployment (never commit secrets).
2. Build or pull an image (for example `ghcr.io/<owner>/<repo>:latest` from CI).
2. Edit **`deployment-api.yaml`** — set `image:` and add `MESH2CAD_*` env (especially `MESH2CAD_STATE_DIR=/data/state`).
3. For **RQ**, deploy Redis (your chart or cloud Redis), set **`MESH2CAD_JOB_BACKEND=rq`**, **`MESH2CAD_REDIS_URL`**, and apply **`deployment-rq-worker.yaml`** with the **same** PVC or an equivalent shared volume.

## Apply

```bash
kubectl apply -f deploy/k8s/pvc.yaml
kubectl apply -f deploy/k8s/deployment-api.yaml
kubectl apply -f deploy/k8s/service-api.yaml
```

See **`docs/scale-out-roadmap.md`** for Postgres, S3, and multi-replica API goals.
