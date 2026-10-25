"""Lightweight TTL-based async memoization decorator (`backend/app/core/memoize.py`).

Caches expensive database or computation results in memory with TTL expiration
and strict size bounding to prevent memory growth.
"""

from __future__ import annotations

import functools
import time
from collections import OrderedDict
from typing import Any, Callable, Coroutine

from app.core.logging import get_logger

logger = get_logger("app.core.memoize")


def async_ttl_cache(ttl_seconds: float = 60.0, maxsize: int = 1000) -> Callable:
    """Decorator for caching async function results with TTL and max size."""

    def decorator(func: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Coroutine[Any, Any, Any]]:
        cache: OrderedDict[tuple, tuple[float, Any]] = OrderedDict()

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Construct a hashable key from args and sorted kwargs
            key = (args, tuple(sorted(kwargs.items())))
            now = time.monotonic()

            if key in cache:
                timestamp, value = cache[key]
                if now - timestamp < ttl_seconds:
                    cache.move_to_end(key)
                    return value
                else:
                    del cache[key]

            result = await func(*args, **kwargs)

            if len(cache) >= maxsize:
                cache.popitem(last=False)  # Evict oldest

            cache[key] = (now, result)
            return result

        return wrapper

    return decorator
