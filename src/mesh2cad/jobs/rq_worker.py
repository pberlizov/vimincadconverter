"""CLI: run an RQ worker for ``mesh2cad`` async jobs."""

from __future__ import annotations

import os
import sys


def main() -> None:
    url = os.environ.get("MESH2CAD_REDIS_URL", "").strip()
    if not url:
        print("MESH2CAD_REDIS_URL is required.", file=sys.stderr)
        raise SystemExit(2)
    try:
        from redis import Redis
        from rq import Queue, Worker
    except ImportError as exc:  # pragma: no cover
        print("Install the queue extra: pip install -e '.[queue]'", file=sys.stderr)
        raise SystemExit(2) from exc

    from mesh2cad.jobs.rq_support import rq_queue_name

    conn = Redis.from_url(url, decode_responses=False)
    name = rq_queue_name()
    queues = [Queue(name, connection=conn)]
    worker = Worker(queues, connection=conn, name=os.environ.get("MESH2CAD_RQ_WORKER_NAME", "mesh2cad-1"))
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
