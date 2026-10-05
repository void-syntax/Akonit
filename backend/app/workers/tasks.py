"""Worker tasks: one function per pipeline stage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models import Signal
from app.models.enums import SignalStatus
from app.notifications.dispatcher import flush_deliveries, notify_matches
from app.services.pipeline_service import (
    refresh_signal_metrics,
    run_collection_cycle,
)
from app.services.radar_service import match_batch
from app.services.retention import run_cleanup

logger = get_logger("worker.tasks")


async def run_collection_task(session: AsyncSession) -> dict:
    """Collect from every source, detect signals, broadcast live updates."""
    from app.api.v1.stream import broadcast_signal

    stats = await run_collection_cycle(
        session,
        countries=await active_countries(session),
        keywords=await collection_keywords(session),
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


async def cleanup_task(session: AsyncSession) -> dict:
    """Retention pass: drop expired unsaved signals and the raw fetch log.

    Runs on its own schedule so the database stays small without the feed
    slowing down.
    """
    return await run_cleanup(session)


async def active_countries(session: AsyncSession) -> list[str]:
    """Countries covered by at least one active radar.

    Falls back to the user's default countries, and finally to a built-in set, so
    a fresh install still collects something instead of running blind.
    """
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

    if not codes:
        codes.update(await default_countries(session))
    if not codes:
        codes.update(settings.default_collect_countries)
    return sorted(codes)


async def default_countries(session: AsyncSession) -> list[str]:
    from app.models import UserProfile

    row = (
        await session.execute(select(UserProfile.default_countries).limit(1))
    ).scalar_one_or_none()
    return [c.upper() for c in (row or []) if c]


async def collection_keywords(session: AsyncSession) -> list[str]:
    """Search terms derived from what the user actually asked for.

    This is what makes the engine tag-driven rather than fixed: the keywords a
    radar or custom tag defines become the queries the collectors run, so
    "Korea + TikTok + Makeup" actually fetches makeup content for Korea instead of
    whatever hardcoded seed happened to be in the adapter.

    Sources come from, in order of precedence:
      * the user's profile defaults;
      * keywords inside active custom tags;
      * nothing, in which case each adapter keeps its own seeds.
    """
    from app.models import CustomTag, Radar, UserProfile

    terms: list[str] = []

    profile = (
        await session.execute(select(UserProfile).limit(1))
    ).scalar_one_or_none()
    if profile and profile.default_tags:
        terms.extend(str(t) for t in profile.default_tags if t)

    custom = (
        (
            await session.execute(
                select(CustomTag).where(CustomTag.is_active.is_(True))
            )
        )
        .scalars()
        .all()
    )
    for tag in custom:
        # A tag's own words are the most specific thing the user has declared.
        terms.extend(str(k) for k in (tag.keywords or []) if k)
        terms.extend(str(a) for a in (tag.aliases or []) if a)
        terms.extend(str(h).lstrip("#") for h in (tag.hashtags or []) if h)

    radars = (
        (
            await session.execute(
                select(Radar).where(Radar.is_active.is_(True))
            )
        )
        .scalars()
        .all()
    )
    for radar in radars:
        terms.extend(str(t) for t in (radar.tag_slugs or []) if t)
        for text in _radar_keyword_conditions(session, radar.id):
            terms.append(text)

    # De-duplicate while preserving order, and keep the list short: a hundred
    # queries per source is slower and gets rate-limited for no benefit.
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        clean = term.strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            out.append(clean)
    return out[: settings.max_collect_keywords]


async def _radar_keyword_conditions(session: AsyncSession, radar_id: str) -> list[str]:
    """Keyword values from a radar's condition tree, if any."""
    from app.models import RadarCondition
    from app.models.enums import ConditionType

    rows = (
        (
            await session.execute(
                select(RadarCondition).where(RadarCondition.radar_id == radar_id)
            )
        )
        .scalars()
        .all()
    )
    out: list[str] = []
    for condition in rows:
        if condition.condition_type != ConditionType.KEYWORD:
            continue
        value = condition.value_json
        if isinstance(value, list):
            out.extend(str(v) for v in value if v)
        elif isinstance(value, str) and value:
            out.append(value)
    return out