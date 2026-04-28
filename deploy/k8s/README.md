# Kubernetes

Starter manifests for **one coordinated API** with **durable async jobs** (Redis + RQ) and a **ReadWriteOnce** PVC for `MESH2CAD_STATE_DIR`.

## Recommended apply (RQ + single Pod API/worker)

The default **`deployment-api.yaml`** runs **two containers in one Pod** (API + `mesh2cad-rq-worker`) so the **same RWO volume** is safe—Kubernetes attaches one PVC once per Pod. A separate **`deployment-rq-worker.yaml`** plus **`deployment-api.yaml`** would require **two Pods** and typically **fails** with RWO or leaves one Pod pending.

```bash
kubectl apply -k deploy/k8s
```

This applies (via **`kustomization.yaml`**): PVC, in-cluster Redis, combined Deployment, Service.

1. Edit **`deployment-api.yaml`** — set both `image:` lines to your registry (for example `ghcr.io/<owner>/<repo>:latest`).
2. Set secrets and production env with **`kubectl create secret`** / **`kubectl set env`** or a private overlay; never commit real API keys.
3. For TLS and a hostname, start from **`ingress.example.yaml`** (copy, edit host, add cert annotations), then apply that file separately.

## Thread-only (no Redis)

For minimal demos (in-process thread pool, no `mesh2cad-rq-worker`):

```bash
kubectl apply -f deploy/k8s/pvc.yaml -f deploy/k8s/deployment-thread.yaml -f deploy/k8s/service-api.yaml
```

Do **not** apply **`deployment-thread.yaml`** and **`deployment-api.yaml`** at the same time: both use **`metadata.name: mesh2cad-api`**. Switch modes by replacing the Deployment.

## Managed Redis

Point **`MESH2CAD_REDIS_URL`** (and keep **`MESH2CAD_JOB_BACKEND=rq`**) at your provider; you can omit **`redis.yaml`** from a custom Kustomize overlay and remove the **`wait-redis`** initContainer if you prefer.

## Separate worker Deployments (advanced)

See **`deployment-rq-worker.yaml`** only when your storage class supports **many writers** (ReadWriteMany / shared filesystem) and you intentionally split API and workers.

## Further reading

- **`docs/operations.md`** — backups, `/ready`, rate limits.
- **`docs/scale-out-roadmap.md`** — Postgres, object storage, multi-replica API.
