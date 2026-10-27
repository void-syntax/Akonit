"""Tests for Server-Sent Events (SSE) Real-Time Telemetry & Signal Stream."""

from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_sse_stream_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/sse/stream")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        
        # Read first chunk
        content = await response.aread()
        assert b"pulse" in content
        assert b"sequence" in content
