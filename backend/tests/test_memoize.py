"""Tests for async TTL memoization decorator."""

from __future__ import annotations

import asyncio
import pytest
from app.core.memoize import async_ttl_cache


@pytest.mark.asyncio
async def test_async_ttl_cache():
    call_count = 0

    @async_ttl_cache(ttl_seconds=0.2, maxsize=10)
    async def expensive_computation(x: int) -> int:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.01)
        return x * 10

    # First call
    res1 = await expensive_computation(5)
    assert res1 == 50
    assert call_count == 1

    # Second call (cached)
    res2 = await expensive_computation(5)
    assert res2 == 50
    assert call_count == 1  # Should not increment

    # Wait for TTL expiration
    await asyncio.sleep(0.25)

    # Third call (expired cache)
    res3 = await expensive_computation(5)
    assert res3 == 50
    assert call_count == 2  # Should increment
