"""Tests for distributed async lock manager."""

from __future__ import annotations

import asyncio
import pytest
from app.core.locks import AsyncDistributedLockManager


@pytest.mark.asyncio
async def test_async_lock_manager():
    manager = AsyncDistributedLockManager()
    lock = await manager.acquire("collector:github")
    
    async with lock:
        assert lock.locked()

    assert not lock.locked()
