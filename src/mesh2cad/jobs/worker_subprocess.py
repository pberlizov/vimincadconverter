"""Shared CLI worker subprocess invocation (thread-pool and RQ worker processes)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from mesh2cad.jobs.exceptions import CANCEL_FILENAME, JobCancelledError, JobTimeoutError


def run_cli_worker_subprocess(*, worker_request: dict[str, Any]) -> dict[str, Any]:
    """Run ``mesh2cad.jobs.worker`` until completion; enforce timeout and cancel file."""
    artifact_path = Path(str(worker_request["artifact_dir"]))
    artifact_path.mkdir(parents=True, exist_ok=True)
    cancel_path = artifact_path.joinpath(CANCEL_FILENAME)
    cancel_path.unlink(missing_ok=True)

    req_path = artifact_path / "worker_request.json"
    req_path.write_text(json.dumps(worker_request), encoding="utf-8")

    timeout_sec = float(os.environ.get("MESH2CAD_JOB_TIMEOUT_SEC", "900"))
    deadline = time.monotonic() + max(5.0, timeout_sec)

    command = [
        sys.executable,
        "-m",
        "mesh2cad.jobs.worker",
        "--worker-request-json",
        str(req_path),
    ]

    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
    )
    try:
        while proc.poll() is None:
            if time.monotonic() > deadline:
                proc.kill()
                try:
                    proc.communicate(timeout=30)
                except (subprocess.TimeoutExpired, ValueError):
                    pass
                raise JobTimeoutError(
                    f"Job exceeded MESH2CAD_JOB_TIMEOUT_SEC={int(timeout_sec)} seconds."
                )
            if cancel_path.exists():
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                try:
                    proc.communicate(timeout=30)
                except (subprocess.TimeoutExpired, ValueError):
                    pass
                raise JobCancelledError("Cancellation was requested for this job.")
            time.sleep(0.15)

        stdout, stderr = proc.communicate(timeout=60)
    except JobCancelledError:
        raise
    except JobTimeoutError:
        raise
    except Exception as exc:
        if proc.poll() is None:
            proc.kill()
        raise RuntimeError(f"Worker subprocess error: {exc}") from exc

    if proc.returncode != 0:
        message = (stderr or "").strip() or (stdout or "").strip() or "Worker subprocess failed."
        raise RuntimeError(message)

    return json.loads(stdout or "{}")
