"""CLI to purge old terminal jobs (free disk; safe for single-node deployments)."""

from __future__ import annotations

import argparse
import os
import sys

from mesh2cad.ui.db import purge_terminal_jobs_older_than


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete completed/failed/cancelled jobs older than N days (DB + on-disk dirs)."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=int(os.environ.get("MESH2CAD_JOB_RETENTION_DAYS", "30")),
        help="Minimum age in days (default 30 or MESH2CAD_JOB_RETENTION_DAYS).",
    )
    args = parser.parse_args()
    n = purge_terminal_jobs_older_than(days=max(1, int(args.days)))
    print(f"Removed {n} job(s).", file=sys.stdout)


if __name__ == "__main__":
    main()
