"""Shared CLI worker subprocess invocation (thread-pool jobs and optional RQ workers)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from mesh2cad.jobs.exceptions import CANCEL_FILENAME, JobCancelledError, JobTimeoutError


def build_worker_command(
    *,
    input_path: str,
    output_dir: str | None,
    artifact_dir: str,
    sample_count: int,
    simplify_target_faces: int | None,
    build: bool,
    auto_tune_sampling: bool,
    align_surface_metrics: bool = True,
    icp_iterations: int = 10,
    icp_seed: int = 0,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "mesh2cad.jobs.worker",
        "--input-path",
        input_path,
        "--artifact-dir",
        artifact_dir,
        "--sample-count",
        str(sample_count),
    ]
    if output_dir is not None:
        command.extend(["--output-dir", output_dir])
    if simplify_target_faces is not None:
        command.extend(["--simplify-target-faces", str(simplify_target_faces)])
    if build:
        command.append("--build")
    if not auto_tune_sampling:
        command.append("--no-auto-tune")
    if not align_surface_metrics:
        command.append("--no-align-surface-metrics")
    command.extend(["--icp-iterations", str(icp_iterations)])
    command.extend(["--icp-seed", str(icp_seed)])
    return command


def run_cli_worker_subprocess(
    *,
    input_path: str,
    output_dir: str | None,
    artifact_dir: str,
    sample_count: int,
    simplify_target_faces: int | None,
    build: bool,
    auto_tune_sampling: bool,
    align_surface_metrics: bool = True,
    icp_iterations: int = 10,
    icp_seed: int = 0,
) -> dict[str, Any]:
    """Run ``mesh2cad.jobs.worker`` until completion; enforce timeout and cancel file."""
    artifact_path = Path(artifact_dir)
    artifact_path.mkdir(parents=True, exist_ok=True)
    cancel_path = artifact_path.joinpath(CANCEL_FILENAME)
    cancel_path.unlink(missing_ok=True)

    timeout_sec = float(os.environ.get("MESH2CAD_JOB_TIMEOUT_SEC", "900"))
    deadline = time.monotonic() + max(5.0, timeout_sec)

    command = build_worker_command(
        input_path=input_path,
        output_dir=output_dir,
        artifact_dir=artifact_dir,
        sample_count=sample_count,
        simplify_target_faces=simplify_target_faces,
        build=build,
        auto_tune_sampling=auto_tune_sampling,
        align_surface_metrics=align_surface_metrics,
        icp_iterations=icp_iterations,
        icp_seed=icp_seed,
    )

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
