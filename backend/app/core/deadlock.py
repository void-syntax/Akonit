"""Asynchronous Deadlock Detector & Transaction Timeout Guard (`backend/app/core/deadlock.py`).

Prevents database transaction hangs and deadlocks in concurrent background runs
with strict timeout protection.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine
from app.core.logging import get_logger

logger = get_logger("app.core.deadlock")


async def with_transaction_timeout(coro: Coroutine[Any, Any, Any], timeout_seconds: float = 10.0) -> Any:
    """Execute database transaction with strict timeout to prevent deadlocks."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.error("Transaction timed out after %.1fs (potential deadlock).", timeout_seconds)
        raise
