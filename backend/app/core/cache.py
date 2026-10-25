"""Redis caching configuration and cache-aside patterns with in-memory fallback.

Implements `backend/app/core/cache.py` to support Redis caching with an
in-memory dict/expiration fallback if Redis is not running locally.
"""

from __future__ import annotations

import asyncio
import json
import pickle
import random
import time
from typing import Any, Callable, TypeVar, Awaitable

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import cache_hits_total, cache_misses_total

logger = get_logger(__name__)

T = TypeVar("T")

# In-memory fallback cache with TTL support: {key: (value, expire_at)}
_memory_cache: dict[str, tuple[Any, float]] = {}

_redis_client: Any | None = None
_redis_lock = asyncio.Lock()


async def get_redis_client() -> Any | None:
    """Get or initialize the redis client async singleton."""
    global _redis_client
    if _redis_client is None and settings.redis_url:
        async with _redis_lock:
            if _redis_client is None:
                try:
                    from redis.asyncio import from_url
                    client = from_url(settings.redis_url, encoding="utf-8", decode_responses=False)
                    await client.ping()
                    _redis_client = client
                    logger.info("cache: redis connected at %s", settings.redis_url)
                except Exception as exc:
                    logger.warning("cache: redis unavailable (%s), using in-memory fallback", exc)
                    _redis_client = None
    return _redis_client


async def close_cache() -> None:
    """Close redis connection if open."""
    global _redis_client
    async with _redis_lock:
        if _redis_client is not None:
            try:
                await _redis_client.aclose()
            except Exception:
                pass
            _redis_client = None


async def clear_memory_cache() -> None:
    """Clear in-memory cache (useful for testing)."""
    _memory_cache.clear()


async def cache_get(key: str) -> Any | None:
    """Get value from cache (Redis with JSON/pickle or fallback to memory)."""
    client = await get_redis_client()
    found = False
    result_val = None
    if client is not None:
        try:
            val = await client.get(key)
            if val is not None:
                try:
                    result_val = json.loads(val.decode("utf-8") if isinstance(val, bytes) else val)
                    found = True
                except Exception:
                    try:
                        result_val = pickle.loads(val if isinstance(val, bytes) else val.encode("latin1"))
                        found = True
                    except Exception as p_exc:
                        logger.warning("cache: failed to deserialize value for key %s: %s", key, p_exc)
        except Exception as exc:
            logger.warning("cache: redis get failed for key %s (%s)", key, exc)

    if not found:
        # In-memory fallback with safe TTL check
        entry = _memory_cache.get(key)
        if entry is not None:
            val, expire_at = entry
            if expire_at > time.time():
                result_val = val
                found = True
            else:
                _memory_cache.pop(key, None)

    if found:
        cache_hits_total.inc()
        return result_val
    else:
        cache_misses_total.inc()
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> None:
    """Set value in cache with TTL and jitter to prevent cache stampedes."""
    jitter = random.randint(-int(ttl_seconds * 0.1), int(ttl_seconds * 0.1)) if ttl_seconds > 10 else 0
    actual_ttl = max(1, ttl_seconds + jitter)

    client = await get_redis_client()
    if client is not None:
        try:
            try:
                serialized = json.dumps(value, default=str)
            except Exception:
                serialized = pickle.dumps(value)
            await client.set(key, serialized, ex=actual_ttl)
            return
        except Exception as exc:
            logger.warning("cache: redis set failed for key %s (%s)", key, exc)

    # In-memory fallback: bound memory size strictly to prevent memory leak
    now = time.time()
    if len(_memory_cache) >= 2000:
        # Purge expired keys
        expired_keys = [k for k, (_, exp) in list(_memory_cache.items()) if exp < now]
        for k in expired_keys:
            _memory_cache.pop(k, None)
        # If still over limit, evict oldest
        if len(_memory_cache) >= 2000:
            excess = len(_memory_cache) - 1800
            for k in list(_memory_cache.keys())[:excess]:
                _memory_cache.pop(k, None)

    _memory_cache[key] = (value, now + actual_ttl)


async def cache_delete(key: str) -> None:
    """Delete key from cache."""
    client = await get_redis_client()
    if client is not None:
        try:
            await client.delete(key)
        except Exception as exc:
            logger.warning("cache: redis delete failed for key %s (%s)", key, exc)

    _memory_cache.pop(key, None)


async def cache_aside(
    key: str,
    fetch_func: Callable[[], Awaitable[T]],
    ttl_seconds: int = 300,
) -> T:
    """Cache-aside pattern: check cache first, otherwise fetch, store, and return."""
    cached = await cache_get(key)
    if cached is not None:
        return cached

    result = await fetch_func()
    if result is not None:
        await cache_set(key, result, ttl_seconds=ttl_seconds)
    return result
