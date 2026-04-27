# Docker deployment

## Quick start

From the repository root:

```bash
docker compose up --build
```

The API listens on port **8000** by default (`MESH2CAD_HOST_PORT` overrides the host mapping). Health checks call **`GET /ready`**, which verifies SQLite and the state directory.

## State directory and scaling

- **`MESH2CAD_STATE_DIR`** (default in the image: `/data/state`) holds the SQLite job database, uploads, and per-job artifacts. Mount a **named volume** or host directory so data survives container restarts.
- **One active replica per state directory.** SQLite and on-disk job layout assume a single writer. Running multiple containers against the same mounted volume without coordination can corrupt the database or interleave uploads.
- **Horizontal scale:** run separate replicas each with its **own** `MESH2CAD_STATE_DIR` (or move to a shared queue and object store). The optional **`[queue]`** extra (`redis`, `rq`) is the intended direction for durable multi-worker setups; see the main README “Single replica vs horizontal scale”.

## Bind address

Inside the container the server binds to **`MESH2CAD_BIND_HOST`** (default `0.0.0.0`) and **`MESH2CAD_BIND_PORT`** (default `8000`). The image runs as a **non-root** user (`mesh2cad`, uid 1000).

## Optional Open3D metrics

Validation can use Open3D’s raycasting scene for point-to-mesh distances when **`MESH2CAD_USE_OPEN3D_METRICS=1`** and `open3d` is installed (e.g. `pip install -e ".[full]"` or an image layer that adds the `open3d` dependency). If Open3D is missing or the path fails, the code falls back to **trimesh** proximity as before.
