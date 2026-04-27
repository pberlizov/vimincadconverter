"""Reject webhook targets that are obviously unsafe (SSRF to internal networks)."""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse


class WebhookUrlRejected(ValueError):
    pass


def validate_webhook_url(url: str | None) -> None:
    """Allow only ``https`` URLs (or ``http`` when ``MESH2CAD_WEBHOOK_ALLOW_HTTP=1``).

    Blocks loopback, link-local, private, and reserved IPs when the host resolves
    to an address (best-effort DNS check). Literal IP hosts are checked without DNS.
    """
    if url is None or not str(url).strip():
        return
    raw = str(url).strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise WebhookUrlRejected("Webhook URL must be an http(s) URL with a host.")
    if parsed.scheme == "http" and os.environ.get("MESH2CAD_WEBHOOK_ALLOW_HTTP", "").lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise WebhookUrlRejected("HTTP webhooks are disabled; use https or set MESH2CAD_WEBHOOK_ALLOW_HTTP=1.")
    host = parsed.hostname
    if host is None:
        raise WebhookUrlRejected("Webhook URL is missing a hostname.")

    _check_host_literal_or_resolved(host)


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _check_host_literal_or_resolved(host: str) -> None:
    try:
        ip = ipaddress.ip_address(host)
        if _is_blocked_ip(ip):
            raise WebhookUrlRejected("Webhook host points to a non-public address.")
        return
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise WebhookUrlRejected(f"Webhook host could not be resolved: {exc}") from exc

    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        addr = sockaddr[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            raise WebhookUrlRejected("Webhook host resolves to a non-public address.")
