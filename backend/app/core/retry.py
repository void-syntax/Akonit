"""HTTP Request Retry & Backoff Decorator (`backend/app/core/retry.py`).

Provides robust exponential backoff and jitter for transient network failures
during external API requests.
"""

from __future__ import annotations

import asyncio
import random
from functools import wraps
from typing import Any, Callable, Coroutine
from app.core.logging import get_logger

logger = get_logger("app.core.retry")


def retry_with_backoff(retries: int = 3, backoff_in_seconds: float = 1.0) -> Callable:
    """Decorator for retrying async operations with exponential backoff and jitter."""

    def decorator(func: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Coroutine[Any, Any, Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            x = 0
            while x < retries:
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    x += 1
                    if x == retries:
                        logger.error("Max retries (%s) exceeded for %s: %s", retries, func.__name__, exc)
                        raise
                    sleep_time = (backoff_in_seconds * (2 ** (x - 1))) + random.uniform(0.05, 0.2)
                    logger.warning("Transient error in %s (attempt %s/%s): %s. Retrying in %.2fs...", func.__name__, x, retries, exc, sleep_time)
                    await asyncio.sleep(sleep_time)

        return wrapper

    return decorator
