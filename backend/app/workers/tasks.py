"""Worker tasks: one function per pipeline stage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import Signal
from app.models.enums import SignalStatus
from app.notifications.dispatcher import flush_deliveries, notify_matches
from app.services.pipeline_service import (
    refresh_signal_metrics,
    run_collection_cycle,
)
from app.services.radar_service import match_batch

logger = get_logger("worker.tasks")


async def run_collection_task(session: AsyncSession) -> dict:
    """Collect from every source, detect signals, broadcast live updates."""
    from app.api.v1.stream import broadcast_signal

    stats = await run_collection_cycle(
        session,
        countries=await active_countries(session),
        limit_per_source=40,
    )

    # push the freshest signals to the live feed
    newest = (
        (
            await session.execute(
                select(Signal)
                .where(Signal.status != SignalStatus.FADING)
                .order_by(Signal.first_seen_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    for signal in newest:
        await broadcast_signal(signal)

    return {
        "fetched": stats.fetched,
        "signals_created": stats.signals_created,
        "signals_updated": stats.signals_updated,
        "sources_ok": stats.sources_ok,
        "sources_failed": stats.sources_failed,
    }


async def run_matching_task(session: AsyncSession) -> dict:
    """Match recent signals against every radar, then queue notifications."""
    outcomes = await match_batch(session, lookback_minutes=180)
    queued = await notify_matches(
        session, signal_ids=[o.signal_id for o in outcomes]
    )
    return {"matched": len(outcomes), "notifications_queued": queued}


async def run_notification_task(session: AsyncSession) -> dict:
    """Flush due notifications (instants, 15-min, hourly, daily digest)."""
    queued = await notify_matches(session)
    result = await flush_deliveries(session)
    return {**result, "queued": queued}


async def refresh_metrics_task(session: AsyncSession) -> int:
    """Recompute growth/acceleration/strength from stored snapshots."""
    return await refresh_signal_metrics(session)


async def active_countries(session: AsyncSession) -> list[str]:
    """Countries covered by at least one active radar."""
    from app.models import Radar

    rows = (
        await session.execute(
            select(Radar.countries).where(Radar.is_active.is_(True))
        )
    ).scalars().all()
    codes: set[str] = set()
    for row in rows:
        if isinstance(row, list):
            codes.update(c.upper() for c in row if c)
    return sorted(codes)