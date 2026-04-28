#!/usr/bin/env python3
"""Set GitHub repository description, homepage, and topics (REST API).

Run from the repo root after authenticating (pick one):

  * ``gh auth login`` — then ``python3 scripts/set_github_repo_metadata.py``
  * Or: ``GITHUB_TOKEN=... python3 scripts/set_github_repo_metadata.py``

Use a classic PAT with the ``repo`` scope, or a fine-grained token with
**Repository administration** read and write for this repository.

Do not paste tokens into chat or commit them. ``--dry-run`` prints actions only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

API = "https://api.github.com"
ACCEPT_JSON = "application/vnd.github+json"
TOPICS_PREVIEW = "application/vnd.github.mercy-preview+json"  # topics API (still works with X-GitHub-Api-Version)

DEFAULT_DESCRIPTION = (
    "Turn STL/OBJ/PLY meshes or point clouds into build123d Python + optional STEP/STL. "
    "CLI, FastAPI, Gradio UI, Redis/RQ jobs, Docker/K8s. MIT."
)
DEFAULT_HOMEPAGE = "https://github.com/pberlizov/ViminCADConverter#readme"
DEFAULT_TOPICS = [
    "cad",
    "mesh",
    "reverse-engineering",
    "stl",
    "step",
    "build123d",
    "parametric-design",
    "python",
    "fastapi",
    "trimesh",
    "point-cloud",
    "3d-printing",
    "computational-geometry",
    "mesh-processing",
    "docker",
    "kubernetes",
    "openapi",
    "gradio",
    "rq",
    "redis",
]


def _parse_owner_repo(remote: str) -> tuple[str, str]:
    remote = remote.strip()
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", remote)
    if not m:
        raise ValueError(f"Could not parse owner/repo from git remote: {remote!r}")
    owner, repo = m.group(1), m.group(2)
    return owner, repo


def _git_remote_url() -> str:
    out = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def _get_token() -> str:
    env = os.environ.get("GITHUB_TOKEN", "").strip()
    if env:
        return env
    try:
        out = subprocess.run(
            ["gh", "auth", "token"],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        out = None
    except subprocess.CalledProcessError:
        out = None
    else:
        tok = out.stdout.strip()
        if tok:
            return tok
    print(
        "No credential found. Set GITHUB_TOKEN or install GitHub CLI and run: gh auth login",
        file=sys.stderr,
    )
    sys.exit(1)


def _request(
    method: str,
    url: str,
    token: str,
    *,
    data: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    body: bytes | None = None
    headers = {
        "Accept": ACCEPT_JSON,
        "Authorization": f"Bearer {token}",
        "User-Agent": "mesh2cad-set-github-repo-metadata",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if extra_headers:
        headers.update(extra_headers)
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.getcode(), raw
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        return exc.getcode(), err_body


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", help="GitHub owner (default: from git remote origin)")
    parser.add_argument("--repo", help="Repository name (default: from git remote origin)")
    parser.add_argument("--description", default=DEFAULT_DESCRIPTION, help="Repository description (max 350 chars)")
    parser.add_argument("--homepage", default=DEFAULT_HOMEPAGE, help="Homepage / website URL")
    parser.add_argument(
        "--topics",
        default=",".join(DEFAULT_TOPICS),
        help="Comma-separated topic names (GitHub replaces all topics with this list)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions only; do not call the API")
    args = parser.parse_args()

    if len(args.description) > 350:
        print("Description exceeds GitHub 350-character limit.", file=sys.stderr)
        sys.exit(1)

    owner, repo = (args.owner, args.repo) if args.owner and args.repo else _parse_owner_repo(_git_remote_url())
    topics = [t.strip() for t in args.topics.split(",") if t.strip()]
    for t in topics:
        if not re.match(r"^[a-z0-9][a-z0-9-]*$", t):
            print(f"Invalid topic name (use lowercase, digits, hyphens): {t!r}", file=sys.stderr)
            sys.exit(1)

    base = f"{API}/repos/{owner}/{repo}"
    print(f"Repository: {owner}/{repo}")
    print(f"Description ({len(args.description)} chars): {args.description[:120]}{'…' if len(args.description) > 120 else ''}")
    print(f"Homepage: {args.homepage}")
    print(f"Topics ({len(topics)}): {', '.join(topics)}")

    if args.dry_run:
        print("Dry run: no API requests sent.")
        return

    token = _get_token()

    code, body = _request(
        "PATCH",
        base,
        token,
        data={"description": args.description, "homepage": args.homepage},
    )
    if code not in (200,):
        print(f"PATCH {base} failed: HTTP {code}\n{body}", file=sys.stderr)
        sys.exit(1)
    print("Updated description and homepage.")

    # Replace all topics (requires mercy preview Accept for older clients; GitHub still honors it)
    code, body = _request(
        "PUT",
        f"{base}/topics",
        token,
        data={"names": topics},
        extra_headers={"Accept": TOPICS_PREVIEW},
    )
    if code not in (200,):
        print(f"PUT topics failed: HTTP {code}\n{body}", file=sys.stderr)
        sys.exit(1)
    print("Updated topics.")


if __name__ == "__main__":
    main()
