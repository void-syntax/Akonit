"""Long-running worker: collects, detects, matches and notifies on a schedule.

This is the "set once, run 24/7" part — no manual steps, self-healing.
"""

from __future__ import annotations

import asyncio
import signal
from contextlib import suppress

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import SessionLocal, init_models
from app.db.session import engine
from app.workers.tasks import (
    cleanup_task,
    refresh_metrics_task,
    run_collection_task,
    run_matching_task,
    run_notification_task,
)

logger = get_logger("worker")

_stop = asyncio.Event()


def _install_signal_handlers() -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, _stop.set)


_GLOBAL_LOCK = asyncio.Lock()  # kept for external callers who might reference it

# Fine-grained per-task locks: collection and notification now run concurrently
# instead of serialising behind a single global lock, so the scheduler stays
# responsive even when one long task (e.g. a slow collection cycle) is running.
_COLLECT_LOCK = asyncio.Lock()
_MATCH_LOCK = asyncio.Lock()
_NOTIFY_LOCK = asyncio.Lock()
_METRICS_LOCK = asyncio.Lock()
_CLEANUP_LOCK = asyncio.Lock()


from opentelemetry import trace

tracer = trace.get_tracer("signal-radar.workers")

async def _cycle_collect() -> None:
    from app.api.v1.system import _WORKER_PAUSED
    if _WORKER_PAUSED:
        logger.info("collection skipped (worker is paused by user)")
        return
    with tracer.start_as_current_span("worker.collect"):
        async with _COLLECT_LOCK:
            async with SessionLocal() as session:
                result = await run_collection_task(session)
                logger.info("collection finished: %s", result)


async def _cycle_match() -> None:
    with tracer.start_as_current_span("worker.match"):
        async with _MATCH_LOCK:
            async with SessionLocal() as session:
                result = await run_matching_task(session)
                logger.info("matching finished: %s", result)


async def _cycle_notify() -> None:
    with tracer.start_as_current_span("worker.notify"):
        async with _NOTIFY_LOCK:
            async with SessionLocal() as session:
                result = await run_notification_task(session)
                logger.info("notifications finished: %s", result)


async def _cycle_metrics() -> None:
    with tracer.start_as_current_span("worker.metrics"):
        async with _METRICS_LOCK:
            async with SessionLocal() as session:
                count = await refresh_metrics_task(session)
                logger.info("metrics refreshed for %d signals", count)


async def _cycle_cleanup() -> None:
    with tracer.start_as_current_span("worker.cleanup"):
        async with _CLEANUP_LOCK:
            async with SessionLocal() as session:
                result = await cleanup_task(session)
                logger.info("cleanup finished: %s", result)


async def main() -> None:
    await init_models()
    _install_signal_handlers()

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _cycle_collect,
        "interval",
        seconds=settings.collect_interval_seconds,
        id="collect",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _cycle_match,
        "interval",
        minutes=5,
        id="match",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _cycle_notify,
        "interval",
        minutes=1,
        id="notify",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _cycle_metrics,
        "interval",
        seconds=settings.snapshot_interval_seconds,
        id="metrics",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _cycle_cleanup,
        "interval",
        minutes=settings.cleanup_interval_minutes,
        id="cleanup",
        max_instances=1,
        coalesce=True,
    )
    # The collection cycle itself skips sources until their declared cadence is
    # due; this tick only keeps fast sources responsive and checks due times.
    scheduler.start()

    logger.info("worker started (collect every %ss)", settings.collect_interval_seconds)

    # run once immediately so the feed is populated on boot
    await _cycle_collect()
    await _cycle_match()

    with suppress(asyncio.CancelledError):
        await _stop.wait()

    scheduler.shutdown(wait=False)
    await engine.dispose()
    logger.info("worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
