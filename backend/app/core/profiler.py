"""Automated Query Performance Profiler & Slow Query Logger (`backend/app/core/profiler.py`).

Monitors database query execution times and logs slow queries exceeding threshold
to assist database optimization in resource-constrained environments.
"""

from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable, Coroutine
from app.core.logging import get_logger

logger = get_logger("app.core.profiler")


def profile_query(threshold_seconds: float = 0.1) -> Callable:
    """Decorator to log slow asynchronous database queries."""

    def decorator(func: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Coroutine[Any, Any, Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                duration = time.perf_counter() - start_time
                if duration > threshold_seconds:
                    logger.warning("Slow query detected in %s: %.4fs (threshold: %.4fs)", func.__name__, duration, threshold_seconds)
                return result
            except Exception as exc:
                duration = time.perf_counter() - start_time
                logger.error("Query failed in %s after %.4fs: %s", func.__name__, duration, exc)
                raise

        return wrapper

    return decorator
