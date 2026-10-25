"""Asynchronous Job Queue & Task Scheduler (`backend/app/core/scheduler.py`).

Schedules periodic background maintenance tasks (vacuum, GC, health sweep)
with asynchronous non-blocking scheduling.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine
from app.core.logging import get_logger

logger = get_logger("app.core.scheduler")


class AsyncBackgroundScheduler:
    """Lightweight periodic task scheduler for background maintenance."""

    def __init__(self) -> None:
        self._tasks: list[asyncio.Task[Any]] = []

    def schedule_interval(self, interval_seconds: float, coro_func: Callable[..., Coroutine[Any, Any, Any]]) -> None:
        """Schedule a coroutine to run periodically in the background."""

        async def worker() -> None:
            while True:
                try:
                    await asyncio.sleep(interval_seconds)
                    await coro_func()
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.error("Scheduled background task failed: %s", exc)

        task = asyncio.create_task(worker())
        self._tasks.append(task)
        logger.info("Scheduled background task interval=%.1fs", interval_seconds)

    def shutdown(self) -> None:
        """Cancel all scheduled background tasks."""
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        logger.info("Background scheduler shut down.")


_scheduler: AsyncBackgroundScheduler | None = None


def get_background_scheduler() -> AsyncBackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncBackgroundScheduler()
        logger.info("AsyncBackgroundScheduler initialized")
    return _scheduler
