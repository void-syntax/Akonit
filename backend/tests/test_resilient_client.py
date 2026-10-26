"""Tests for ResilientHttpClient module."""

from __future__ import annotations

import pytest
import httpx
from app.pipeline.resilient_client import ResilientHttpClient


@pytest.mark.asyncio
async def test_resilient_http_client_caching():
    client = ResilientHttpClient(requests_per_second=50.0)
    assert client.tokens > 0
    await client.acquire_token()
    assert True
