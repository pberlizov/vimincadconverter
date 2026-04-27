"""Post job completion webhooks (optional ``httpx``; falls back to ``urllib``)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import urllib.request
from typing import Any

from mesh2cad.security.webhook_url import WebhookUrlRejected, validate_webhook_url
from mesh2cad.ui.db import get_job


def schedule_job_webhook(job_id: str) -> None:
    """Fire-and-forget webhook for terminal job states when configured."""
    thread = threading.Thread(target=_deliver_webhook_safe, args=(job_id,), daemon=True)
    thread.start()


def _deliver_webhook_safe(job_id: str) -> None:
    try:
        _deliver_webhook(job_id)
    except Exception:
        pass


def _deliver_webhook(job_id: str) -> None:
    job = get_job(job_id)
    if job is None:
        return
    req = job.get("request") or {}
    url = req.get("webhook_url")
    if not url or not isinstance(url, str):
        return
    try:
        validate_webhook_url(url)
    except WebhookUrlRejected:
        return
    secret = os.environ.get("MESH2CAD_WEBHOOK_SECRET", "").strip()
    body_obj: dict[str, Any] = {
        "job_id": job_id,
        "status": job.get("status"),
        "warnings": job.get("warnings", []),
        "step_path": job.get("step_path"),
        "source_path": job.get("source_path"),
        "payload": job.get("payload") or {},
    }
    body = json.dumps(body_obj, default=str).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if secret:
        sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers["X-Mesh2cad-Signature"] = f"sha256={sig}"

    try:
        import httpx

        httpx.post(url, content=body, headers=headers, timeout=30.0)
    except ImportError:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as resp:
                resp.read()
        except Exception:
            return
    except Exception:
        return
