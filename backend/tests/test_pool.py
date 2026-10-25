"""Tests for connection pool pruner module."""

from __future__ import annotations

import pytest
from app.core.database import engine
from app.core.pool import prune_connection_pool


@pytest.mark.asyncio
async def test_prune_connection_pool():
    stats = await prune_connection_pool(engine)
    assert "pool_size" in stats
    assert "checked_out" in stats
