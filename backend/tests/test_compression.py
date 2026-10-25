"""Tests for compression middleware configuration."""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_compression_middleware():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/telemetry/metrics", headers={"Accept-Encoding": "gzip"})
        assert response.status_code == 200
