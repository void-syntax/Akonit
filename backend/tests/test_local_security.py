"""Regression checks for local-only auth mode and webhook URL boundaries."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.core.webhook_url import UnsafeWebhookURL, validate_public_https_url
from app.main import app


def test_shared_host_auth_cannot_be_enabled_without_an_auth_flow():
    with pytest.raises(ValidationError, match="Shared-host authentication"):
        Settings(auth_disabled=False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/hook",
        "https://127.0.0.1/hook",
        "https://169.254.169.254/latest/meta-data",
        "https://user:pass@example.com/hook",
        "https://example.com:0/hook",
    ],
)
async def test_webhook_validator_rejects_unsafe_urls(url: str):
    with pytest.raises(UnsafeWebhookURL):
        await validate_public_https_url(url)


@pytest.mark.asyncio
async def test_webhook_validator_accepts_public_ip_https_url():
    url = "https://1.1.1.1/webhook"
    assert await validate_public_https_url(url) == url


@pytest.mark.asyncio
async def test_local_api_rejects_untrusted_host_and_cross_origin_writes():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        bad_host = await client.get(
            "/health", headers={"Host": "attacker.example"}
        )
        bad_origin = await client.post(
            "/missing", headers={"Origin": "https://attacker.example"}
        )

    assert bad_host.status_code == 400
    assert bad_origin.status_code == 403
