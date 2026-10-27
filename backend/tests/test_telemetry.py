"""Tests for telemetry and diagnostics API endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_telemetry_metrics_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/telemetry/metrics")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "deduplication" in data
        assert "clustering" in data
        assert "memory_guard" in data
        assert "database" in data
        assert "signals" in data and "total" in data["signals"]
        assert "sources" in data and "active_24h" in data["sources"]
