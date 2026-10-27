"""Asynchronous Circuit Breaker Fallback Wrapper (`backend/app/core/fallback.py`).

Provides graceful fallback execution for data collection and API operations
when primary sources or circuit breakers trip.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine
from app.core.logging import get_logger

logger = get_logger("app.core.fallback")


async def with_fallback(primary_coro: Coroutine[Any, Any, Any], fallback_func: Callable[..., Any], *fallback_args: Any) -> Any:
    """Execute primary coroutine with graceful fallback on failure."""
    try:
        return await primary_coro
    except Exception as exc:
        logger.warning("Primary operation failed (%s). Executing graceful fallback...", exc)
        if callable(fallback_func):
            if asyncio.iscoroutinefunction(fallback_func):
                return await fallback_func(*fallback_args)
            return fallback_func(*fallback_args)
        return fallback_func
