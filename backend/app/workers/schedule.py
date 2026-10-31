"""Long-running worker: collects, detects, matches and notifies on a schedule.

This is the "set once, run 24/7" part — no manual steps, self-healing.
"""

from __future__ import annotations

import asyncio
import os
import signal
from contextlib import suppress
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from opentelemetry import trace

from app.core.config import settings
from app.core.logging import get_logger
from app.core.worker_control import (
    acquire_worker_lock,
    consume_immediate_collection,
    request_immediate_collection,
    write_worker_status,
)
from app.db.session import SessionLocal, init_models
from app.db.session import engine
from app.workers.tasks import (
    cleanup_task,
    refresh_metrics_task,
    run_collection_task,
    run_matching_task,
    run_notification_task,
    run_laya_task,
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
_LAYA_LOCK = asyncio.Lock()


tracer = trace.get_tracer("signal-radar.workers")


async def _cycle_collect() -> None:
    from app.core.worker_control import is_worker_paused

    if is_worker_paused():
        logger.info("collection skipped (worker is paused by user)")
        write_worker_status(collection_state="paused")
        return
    with tracer.start_as_current_span("worker.collect"):
        async with _COLLECT_LOCK:
            started_at = datetime.now(UTC).isoformat()
            write_worker_status(
                status="running",
                collection_state="running",
                last_collection_started_at=started_at,
                last_collection_error=None,
            )
            force_collection = consume_immediate_collection()
            try:
                async with SessionLocal() as session:
                    result = await run_collection_task(
                        session, force=force_collection
                    )
            except Exception as exc:
                if force_collection:
                    request_immediate_collection()
                # APScheduler can retry a job next interval, but an uncaught
                # first-cycle exception used to terminate the worker at startup.
                kind = type(exc).__name__
                write_worker_status(
                    collection_state="idle",
                    last_collection_completed_at=datetime.now(UTC).isoformat(),
                    last_collection_error=kind,
                )
                logger.error("collection cycle failed (%s)", kind)
                return

            completed_at = datetime.now(UTC).isoformat()
            status_update = {
                "status": "running",
                "collection_state": "idle",
                "last_collection_error": None,
            }
            # A one-minute scheduler tick often finds no adapter due. Preserve
            # the last real pass instead of replacing its useful counters with
            # an all-zero idle tick (which made the UI look stuck).
            if result.get("sources_due", 0) > 0:
                status_update.update(
                    last_collection_completed_at=completed_at,
                    last_collection_result=result,
                )
            else:
                status_update["last_scheduler_tick_at"] = completed_at
            write_worker_status(**status_update)
            logger.info("collection finished: %s", result)


async def _cycle_heartbeat() -> None:
    write_worker_status(status="running", pid=os.getpid())


async def _cycle_match() -> None:
    with tracer.start_as_current_span("worker.match"):
        async with _MATCH_LOCK:
            try:
                async with SessionLocal() as session:
                    result = await run_matching_task(session)
                    # match_batch commits RadarSignal rows before notification
                    # deliveries are queued. Persist those new delivery rows
                    # before closing this session or they disappear silently.
                    await session.commit()
            except Exception as exc:
                logger.error("matching cycle failed (%s)", type(exc).__name__)
                return
            logger.info("matching finished: %s", result)


async def _cycle_notify() -> None:
    with tracer.start_as_current_span("worker.notify"):
        async with _NOTIFY_LOCK:
            try:
                async with SessionLocal() as session:
                    result = await run_notification_task(session)
                    # Persist SENT / FAILED / SKIPPED status and attempt counts.
                    await session.commit()
            except Exception as exc:
                logger.error("notification cycle failed (%s)", type(exc).__name__)
                return
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


async def _cycle_laya() -> None:
    if not settings.ai_classification_enabled:
        return
    async with _LAYA_LOCK:
        try:
            async with SessionLocal() as session:
                classified = await run_laya_task(session)
            if classified:
                logger.info("Laya classified one signal")
        except Exception as exc:
            logger.warning("Laya background cycle failed (%s)", type(exc).__name__)


async def main() -> None:
    lock = acquire_worker_lock()
    if lock is None:
        logger.warning("worker already running; second instance will exit")
        return

    scheduler = None
    write_worker_status(
        status="starting",
        pid=os.getpid(),
        started_at=datetime.now(UTC).isoformat(),
        collection_state="idle",
        last_collection_error=None,
    )
    try:
        await init_models()
        from app.services.pipeline_service import (
            normalize_legacy_google_news_metrics,
            normalize_unconfirmed_ai_critical,
        )

        async with SessionLocal() as session:
            normalized = await normalize_legacy_google_news_metrics(session)
            downgraded = await normalize_unconfirmed_ai_critical(session)
        if normalized:
            logger.info("normalized %d legacy unmeasured Google News signals", normalized)
        if downgraded:
            logger.info(
                "downgraded %d unsupported AI critical labels", downgraded
            )
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
        scheduler.add_job(
            _cycle_laya,
            "interval",
            seconds=60,
            id="laya",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            _cycle_heartbeat,
            "interval",
            seconds=15,
            id="heartbeat",
            max_instances=1,
            coalesce=True,
        )
        # Each collector keeps its own cadence; this tick only checks which
        # sources are due, so cheap intervals do not mean every source is hit.
        scheduler.start()
        write_worker_status(status="running", pid=os.getpid())
        logger.info(
            "worker started (collect scheduler tick every %ss)",
            settings.collect_interval_seconds,
        )

        # Populate the feed immediately, then keep the scheduler alive.
        await _cycle_collect()
        await _cycle_match()
        with suppress(asyncio.CancelledError):
            await _stop.wait()
    finally:
        if scheduler is not None and scheduler.running:
            scheduler.shutdown(wait=False)
        write_worker_status(
            status="stopped",
            pid=None,
            collection_state="idle",
            stopped_at=datetime.now(UTC).isoformat(),
        )
        await engine.dispose()
        lock.close()
        logger.info("worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
