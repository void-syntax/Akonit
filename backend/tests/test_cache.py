"""Tests for Redis caching and cache-aside implementation."""

from __future__ import annotations

import asyncio
import pytest
from app.core.cache import cache_get, cache_set, cache_delete, cache_aside, close_cache


@pytest.mark.asyncio
async def test_cache_set_get():
    await cache_delete("test:key:1")
    val = await cache_get("test:key:1")
    assert val is None

    await cache_set("test:key:1", {"hello": "world"}, ttl_seconds=60)
    val = await cache_get("test:key:1")
    assert val == {"hello": "world"}

    await cache_delete("test:key:1")
    assert await cache_get("test:key:1") is None


@pytest.mark.asyncio
async def test_cache_aside_pattern():
    key = "test:aside:1"
    await cache_delete(key)

    call_count = 0

    async def fetch():
        nonlocal call_count
        call_count += 1
        return "computed-value"

    # First call: should miss cache and call fetch
    res1 = await cache_aside(key, fetch, ttl_seconds=60)
    assert res1 == "computed-value"
    assert call_count == 1

    # Second call: should hit cache without calling fetch
    res2 = await cache_aside(key, fetch, ttl_seconds=60)
    assert res2 == "computed-value"
    assert call_count == 1

    await cache_delete(key)
    await close_cache()
