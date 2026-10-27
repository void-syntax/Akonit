"""Tests for sentinel dashboard health aggregation."""

from __future__ import annotations

import pytest
from app.core.sentinel_dashboard import get_sentinel_dashboard_status


@pytest.mark.asyncio
async def test_sentinel_dashboard_status():
    status = await get_sentinel_dashboard_status()
    assert status["status"] == "fully_operational"
    assert "collectors" in status
    assert "deduplication" in status
    assert "memory_ring_buffer" in status
