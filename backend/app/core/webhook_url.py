"""Validation for URLs the server contacts on a user's behalf."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeWebhookURL(ValueError):
    """Raised when a webhook URL could target a local or non-HTTPS service."""


async def validate_public_https_url(value: object) -> str:
    """Accept only HTTPS URLs resolving exclusively to globally routable IPs."""
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise UnsafeWebhookURL("Webhook URL is missing or too long")

    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
        if port is None:
            port = 443
    except ValueError as exc:
        raise UnsafeWebhookURL("Webhook URL is malformed") from exc

    if (
        parsed.scheme.lower() != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not (1 <= port <= 65535)
        or (parsed.netloc and parsed.netloc.endswith(":0"))
    ):
        raise UnsafeWebhookURL("Webhook URL must be a public HTTPS address")

    try:
        addresses = {ipaddress.ip_address(hostname)}
    except ValueError:
        try:
            loop = asyncio.get_running_loop()
            records = await asyncio.wait_for(
                loop.getaddrinfo(hostname, port, type=socket.SOCK_STREAM), timeout=3
            )
            addresses = {
                ipaddress.ip_address(record[4][0]) for record in records
            }
        except (OSError, TimeoutError, ValueError) as exc:
            raise UnsafeWebhookURL("Webhook host could not be resolved safely") from exc

    if not addresses or any(not address.is_global for address in addresses):
        raise UnsafeWebhookURL("Webhook host must resolve only to public addresses")

    return value
