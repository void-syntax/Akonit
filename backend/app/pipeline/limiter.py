"""Async Event Pipeline Concurrency Limiter & Semaphore (`backend/app/pipeline/limiter.py`).

Prevents resource exhaustion and CPU spikes on resource-constrained laptops
by bounding concurrent collector requests and embedding tasks.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine
from app.core.logging import get_logger

logger = get_logger("app.pipeline.limiter")


class PipelineConcurrencyLimiter:
    """Semaphore-based concurrency limiter for background pipeline workers."""

    def __init__(self, max_concurrent: int = 5) -> None:
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def run(self, coro_func: Callable[..., Coroutine[Any, Any, Any]], *args: Any, **kwargs: Any) -> Any:
        """Execute coroutine under strict concurrency semaphore limit."""
        async with self.semaphore:
            return await coro_func(*args, **kwargs)


_limiter: PipelineConcurrencyLimiter | None = None


def get_pipeline_limiter() -> PipelineConcurrencyLimiter:
    global _limiter
    if _limiter is None:
        _limiter = PipelineConcurrencyLimiter(max_concurrent=5)
        logger.info("PipelineConcurrencyLimiter initialized (max_concurrent=5)")
    return _limiter
