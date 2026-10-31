"""Signal feed, detail and history endpoints."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import Text, case, cast, func, or_, select

from app.api.deps import CurrentUser, OptionalUser, SessionDep
from app.core.config import settings
from app.models import (
    IgnoredSignal,
    Radar,
    RadarSignal,
    SavedSignal,
    Signal,
    SignalSnapshot,
)
from app.models.enums import SignalStatus
from app.schemas.api import IntelligenceBriefingOut, SignalDetail, SignalOut, SignalPage

router = APIRouter(prefix="/signals", tags=["signals"])


def _evidence_tier():
    """SQL ordering tier: corroborated, measured, then unmeasured mentions."""
    return case(
        (Signal.cross_source_count > 1, 0),
        (
            or_(
                Signal.current_activity > 0,
                Signal.previous_activity > 0,
                Signal.growth > 0,
            ),
            1,
        ),
        else_=2,
    )


def _apply_user_flags(
    page: list[Signal], saved_ids: set[str], ignored_ids: set[str]
) -> list[SignalOut]:
    return [
        SignalOut(
            **{
                field: getattr(signal, field)
                for field in SignalOut.model_fields
                if hasattr(signal, field)
            },
            is_saved=signal.id in saved_ids,
            is_ignored=signal.id in ignored_ids,
        )
        for signal in page
    ]


async def _user_sets(
    session: SessionDep, user_id: str | None, signal_ids: list[str]
) -> tuple[set[str], set[str]]:
    if not user_id or not signal_ids:
        return set(), set()
    saved = (
        (
            await session.execute(
                select(SavedSignal.signal_id).where(
                    SavedSignal.user_id == user_id,
                    SavedSignal.signal_id.in_(signal_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    ignored = (
        (
            await session.execute(
                select(IgnoredSignal.signal_id).where(
                    IgnoredSignal.user_id == user_id,
                    IgnoredSignal.signal_id.in_(signal_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    return set(saved), set(ignored)


@router.get("", response_model=SignalPage)
async def list_signals(
    session: SessionDep,
    user: OptionalUser,
    tab: str = Query(default="all"),
    status_filter: list[SignalStatus] | None = Query(default=None, alias="status"),
    country: list[str] | None = Query(default=None),
    source: list[str] | None = Query(default=None),
    radar_id: str | None = None,
    tag: list[str] | None = Query(default=None),
    keyword: str | None = None,
    min_strength: float | None = None,
    max_age_minutes: float | None = None,
    limit: int = Query(default=30, le=100),
    offset: int = 0,
):
    """Public feed with cache-aside pattern."""
    from app.core.cache import cache_aside
    import json
    import hashlib

    # Build cache key based on query parameters and user presence/id (if saved tab)
    user_key_part = f"user:{user.id}" if user and tab == "saved" else "anon"
    params_dict = {
        "tab": tab,
        "status": [s.value for s in status_filter] if status_filter else None,
        "country": country,
        "source": source,
        "radar_id": radar_id,
        "tag": tag,
        "keyword": keyword,
        "min_strength": min_strength,
        "max_age_minutes": max_age_minutes,
        "limit": limit,
        "offset": offset,
        "user_part": user_key_part,
    }
    cache_key = f"signals:list:{hashlib.md5(json.dumps(params_dict, sort_keys=True, default=str).encode('utf-8')).hexdigest()}"

    async def _fetch():
        statement = select(Signal)

        if tab == "rising":
            statement = statement.where(
                Signal.status.in_([SignalStatus.RISING, SignalStatus.BREAKOUT])
            )
        elif tab == "breakout":
            statement = statement.where(Signal.status == SignalStatus.BREAKOUT)
        elif tab == "new":
            statement = statement.where(Signal.status == SignalStatus.NEW)
        elif tab == "discover":
            statement = statement.where(
                Signal.status.in_(
                    [
                        SignalStatus.NEW,
                        SignalStatus.RISING,
                        SignalStatus.BREAKOUT,
                    ]
                )
            )
        elif tab == "saved":
            if user is None:
                return {"items": [], "total": 0, "limit": limit, "offset": offset}
            statement = statement.join(
                SavedSignal, SavedSignal.signal_id == Signal.id
            ).where(SavedSignal.user_id == user.id)

        # The live feed is for early signals. Old saved items remain available
        # in the Saved tab; stale unsaved trends should not outrank fresh ones.
        if tab != "saved":
            freshness_cutoff = datetime.now(UTC) - timedelta(
                hours=settings.signal_ttl_hours
            )
            statement = statement.where(
                Signal.first_seen_at >= freshness_cutoff,
                Signal.last_seen_at >= freshness_cutoff,
            )

        if status_filter:
            statement = statement.where(Signal.status.in_(status_filter))
        if country:
            statement = statement.where(Signal.country_code.in_([c.upper() for c in country]))
        if source:
            statement = statement.where(Signal.source_id.in_(source))
        if min_strength is not None:
            statement = statement.where(Signal.strength >= min_strength)
        if max_age_minutes is not None:
            cutoff = datetime.now(UTC) - timedelta(minutes=max_age_minutes)
            statement = statement.where(Signal.first_seen_at >= cutoff)
        if keyword:
            escaped = keyword.replace("%", r"\%").replace("_", r"\_")
            pattern = f"%{escaped.lower()}%"
            statement = statement.where(
                func.lower(Signal.title).like(pattern)
                | func.lower(Signal.description).like(pattern)
            )
        if radar_id:
            if user is None:
                raise HTTPException(status_code=401, detail="Not authenticated")
            radar = (
                await session.execute(
                    select(Radar).where(
                        Radar.id == radar_id, Radar.user_id == user.id
                    )
                )
            ).scalar_one_or_none()
            if radar is None:
                raise HTTPException(status_code=404, detail="Radar not found")
            statement = statement.join(
                RadarSignal, RadarSignal.signal_id == Signal.id
            ).where(RadarSignal.radar_id == radar_id)

        if tag:
            needles = [f'"{t.lower()}"' for t in tag if t]
            if needles:
                serialised = cast(Signal.keywords, Text)
                statement = statement.where(
                    or_(*[serialised.like(f"%{n}%") for n in needles])
                )

        total = (
            await session.execute(select(func.count()).select_from(statement.subquery()))
        ).scalar_one()
        rows = (
            (
                await session.execute(
                    statement.order_by(
                        # Rank evidence quality before the heuristic activity
                        # score: a lone, unmeasured headline must not outrank
                        # a measured trend or an independently corroborated
                        # event just because both are fresh.
                        _evidence_tier(),
                        # A formerly strong signal that is now FADING must not
                        # sit above fresh live discoveries just because its
                        # historical score has not decayed yet.
                        case(
                            (Signal.status == SignalStatus.BREAKOUT, 0),
                            (Signal.status == SignalStatus.RISING, 1),
                            (Signal.status == SignalStatus.NEW, 2),
                            else_=3,
                        ),
                        Signal.strength.desc(),
                        Signal.cross_source_count.desc(),
                        Signal.last_seen_at.desc(),
                        Signal.first_seen_at.desc(),
                    )
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .unique()
            .all()
        )

        saved_ids, ignored_ids = await _user_sets(
            session, user.id if user else None, [s.id for s in rows]
        )

        # Serialize signal objects to dicts or primitive data so they can be cached properly
        serialized_items = _apply_user_flags(list(rows), saved_ids, ignored_ids)
        return {
            "items": [item.model_dump() for item in serialized_items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    cached_data = await cache_aside(cache_key, _fetch, ttl_seconds=60)
    if isinstance(cached_data, dict):
        # Convert items back to SignalOut objects
        items = [SignalOut(**item) for item in cached_data["items"]]
        return SignalPage(
            items=items,
            total=cached_data["total"],
            limit=cached_data["limit"],
            offset=cached_data["offset"],
        )
    return cached_data


@router.get("/{signal_id}", response_model=SignalDetail)
async def signal_detail(signal_id: str, session: SessionDep, user: OptionalUser):
    signal = (
        (
            await session.execute(
                select(Signal)
                .where(Signal.id == signal_id)
            )
        )
        .scalar_one_or_none()
    )
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")

    snapshots = (
        await session.execute(
            select(SignalSnapshot)
            .where(SignalSnapshot.signal_id == signal.id)
            .order_by(SignalSnapshot.captured_at.desc())
            .limit(500)
        )
    ).scalars().all()
    snapshots.reverse()

    saved_ids, ignored_ids = await _user_sets(
        session, user.id if user else None, [signal.id]
    )
    base = SignalOut(
        **{
            field: getattr(signal, field)
            for field in SignalOut.model_fields
            if hasattr(signal, field)
        },
        is_saved=signal.id in saved_ids,
        is_ignored=signal.id in ignored_ids,
    )
    return SignalDetail(
        **base.model_dump(),
        source_metadata=signal.source_metadata or {},
        snapshots=[
            {
                "captured_at": s.captured_at,
                "activity": s.activity,
                "previous_activity": s.previous_activity,
                "growth": s.growth,
                "acceleration": s.acceleration,
                "strength": s.strength,
                "status": s.status,
                "rank": s.rank,
            }
            for s in snapshots
        ],
    )


@router.get("/{signal_id}/related", response_model=list[SignalOut])
async def related_signals(
    signal_id: str,
    session: SessionDep,
    user: OptionalUser,
    limit: int = Query(default=6, le=20),
):
    """Signals sharing tags, country or source with this one."""
    base = await _get_signal(session, signal_id)
    base_tags = set(base.keywords or [])

    candidates = (
        (
            await session.execute(
                select(Signal)
                .where(
                    Signal.id != base.id,
                    Signal.status != SignalStatus.FADING,
                )
                .order_by(Signal.strength.desc())
                .limit(400)
            )
        )
        .scalars()
        .unique()
        .all()
    )

    scored: list[tuple[int, Signal]] = []
    for other in candidates:
        score = 0
        if base_tags & set(other.keywords or []):
            score += 3 * len(base_tags & set(other.keywords or []))
        if base.country_code and other.country_code == base.country_code:
            score += 2
        if other.source_id == base.source_id:
            score += 1
        if score:
            scored.append((score, other))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    top = [signal for _, signal in scored[:limit]]

    saved_ids, ignored_ids = await _user_sets(
        session, user.id if user else None, [s.id for s in top]
    )
    return _apply_user_flags(top, saved_ids, ignored_ids)


@router.get("/{signal_id}/history")
async def signal_history(
    signal_id: str,
    session: SessionDep,
    hours: int = Query(default=168, le=720),
):
    """Chart data derived from the append-only snapshot table."""
    await _get_signal(session, signal_id)
    since = datetime.now(UTC) - timedelta(hours=hours)
    rows = (
        (
            await session.execute(
                select(SignalSnapshot)
                .where(
                    SignalSnapshot.signal_id == signal_id,
                    SignalSnapshot.captured_at >= since,
                )
                .order_by(SignalSnapshot.captured_at)
            )
        )
        .scalars()
        .all()
    )
    return {
        "signal_id": signal_id,
        "points": [
            {
                "t": s.captured_at,
                "activity": s.activity,
                "growth": s.growth,
                "acceleration": s.acceleration,
                "strength": s.strength,
                "status": s.status.value,
            }
            for s in rows
        ],
    }


@router.get("/{signal_id}/briefing", response_model=IntelligenceBriefingOut)
async def get_signal_briefing(signal_id: str, session: SessionDep):
    """Get or create a lightweight, evidence-aware signal summary."""
    from app.models.signals import IntelligenceBriefing
    from app.ai.deep_briefing import synthesize_deep_briefing

    await _get_signal(session, signal_id)
    briefing = (
        await session.execute(
            select(IntelligenceBriefing).where(IntelligenceBriefing.signal_id == signal_id)
        )
    ).scalar_one_or_none()

    if briefing is None:
        # Try synthesizing on demand
        briefing = await synthesize_deep_briefing(session, signal_id)

    if briefing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Intelligence briefing not available for this signal (requires critical/unicorn status or high strength).",
        )
    return briefing


@router.post("/{signal_id}/save", response_model=SignalOut)
async def save_signal(signal_id: str, session: SessionDep, user: CurrentUser):
    signal = await _get_signal(session, signal_id)
    existing = (
        await session.execute(
            select(SavedSignal).where(
                SavedSignal.user_id == user.id,
                SavedSignal.signal_id == signal_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(SavedSignal(user_id=user.id, signal_id=signal_id))
        await session.commit()
    saved_ids, ignored_ids = await _user_sets(session, user.id, [signal_id])
    return _apply_user_flags([signal], saved_ids, ignored_ids)[0]


@router.delete("/{signal_id}/save", status_code=status.HTTP_204_NO_CONTENT)
async def unsave_signal(signal_id: str, session: SessionDep, user: CurrentUser):
    row = (
        await session.execute(
            select(SavedSignal).where(
                SavedSignal.user_id == user.id,
                SavedSignal.signal_id == signal_id,
            )
        )
    ).scalar_one_or_none()
    if row:
        await session.delete(row)
        await session.commit()


@router.post("/{signal_id}/mute", response_model=SignalOut)
async def mute_signal(signal_id: str, session: SessionDep, user: CurrentUser):
    signal = await _get_signal(session, signal_id)
    existing = (
        await session.execute(
            select(IgnoredSignal).where(
                IgnoredSignal.user_id == user.id,
                IgnoredSignal.signal_id == signal_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            IgnoredSignal(user_id=user.id, signal_id=signal_id, reason="muted")
        )
        await session.commit()
    saved_ids, ignored_ids = await _user_sets(session, user.id, [signal_id])
    return _apply_user_flags([signal], saved_ids, ignored_ids)[0]


@router.delete("/{signal_id}/mute", status_code=status.HTTP_204_NO_CONTENT)
async def unmute_signal(signal_id: str, session: SessionDep, user: CurrentUser):
    row = (
        await session.execute(
            select(IgnoredSignal).where(
                IgnoredSignal.user_id == user.id,
                IgnoredSignal.signal_id == signal_id,
            )
        )
    ).scalar_one_or_none()
    if row:
        await session.delete(row)
        await session.commit()


@router.delete("/all")
async def clear_all_collected_signals(session: SessionDep, _user: CurrentUser):
    """Reset collected signal data and request one fresh worker pass."""
    from sqlalchemy import delete

    from app.core.cache import cache_delete_prefix
    from app.core.worker_control import (
        is_worker_paused,
        read_worker_status,
        request_immediate_collection,
        set_worker_paused,
        write_worker_status,
    )
    from app.models.notifications import NotificationDelivery, SourceHealth
    from app.models.signals import IntelligenceBriefing
    from app.models.tags import SignalTag
    from app.models.taxonomy import Source, SourceEvent
    from app.pipeline.dlq import FailedSignal

    was_paused = is_worker_paused()
    if not was_paused:
        set_worker_paused(True)

    try:
        # Let an in-flight collection finish before removing its database rows.
        # The pause flag prevents a new scheduled cycle from starting meanwhile.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(settings.source_fetch_timeout_seconds * 2 + 10, 60)
        while True:
            worker = read_worker_status()
            collecting = (
                worker.get("status") == "running"
                and worker.get("collection_state") == "running"
            )
            if not collecting:
                await asyncio.sleep(0.25)
                worker = read_worker_status()
                if not (
                    worker.get("status") == "running"
                    and worker.get("collection_state") == "running"
                ):
                    break
            if loop.time() >= deadline:
                raise HTTPException(
                    status_code=409,
                    detail="Collector is still finishing its current pass. Try again shortly.",
                )
            await asyncio.sleep(0.25)

        signal_count = (
            await session.execute(select(func.count()).select_from(Signal))
        ).scalar_one()
        event_count = (
            await session.execute(select(func.count()).select_from(SourceEvent))
        ).scalar_one()
        snapshot_count = (
            await session.execute(select(func.count()).select_from(SignalSnapshot))
        ).scalar_one()

        # Remove the history and all links that could make old results reappear.
        await session.execute(delete(SourceEvent))
        await session.execute(delete(FailedSignal))
        await session.execute(delete(SignalSnapshot))
        await session.execute(delete(SavedSignal))
        await session.execute(delete(IgnoredSignal))
        await session.execute(delete(RadarSignal))
        await session.execute(delete(SignalTag))
        await session.execute(delete(NotificationDelivery))
        await session.execute(delete(IntelligenceBriefing))
        await session.execute(delete(Signal))

        # Reset collection counters so the next source-health report describes
        # the new experiment rather than mixing it with the old run.
        source_rows = (await session.execute(select(Source))).scalars().all()
        for source in source_rows:
            source.records_fetched = 0
            source.total_records = 0
            source.last_fetch = None
            source.last_success = None
        health_rows = (await session.execute(select(SourceHealth))).scalars().all()
        for health in health_rows:
            health.records_last_hour = 0
            health.avg_duration_ms = 0.0
            health.last_check_at = None
            health.healthy_since = None
            health.strategy = None
        radar_rows = (await session.execute(select(Radar))).scalars().all()
        for radar in radar_rows:
            radar.match_count = 0
            radar.last_matched_at = None
            radar.last_notified_at = None

        await session.commit()

        await cache_delete_prefix("signals:list:")
        write_worker_status(
            last_collection_started_at=None,
            last_collection_completed_at=None,
            last_collection_result=None,
            last_collection_error=None,
        )
        request_immediate_collection()
        return {
            "deleted_signals": signal_count,
            "deleted_source_events": event_count,
            "deleted_snapshots": snapshot_count,
            "collection_queued": True,
        }
    except Exception:
        await session.rollback()
        raise
    finally:
        if not was_paused:
            set_worker_paused(False)


@router.delete("/{signal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_signal(signal_id: str, session: SessionDep, user: OptionalUser):
    """Delete a signal and all its related references (snapshots, saves, mutes, radar matches)."""
    from sqlalchemy import delete
    from app.models.signals import SignalSnapshot
    from app.models.notifications import SavedSignal, IgnoredSignal
    from app.models.radars import RadarSignal
    from app.models.tags import SignalTag
    from app.models.taxonomy import SourceEvent

    signal = await _get_signal(session, signal_id)

    # Clean up dependent records safely across all SQL dialects
    await session.execute(delete(SignalSnapshot).where(SignalSnapshot.signal_id == signal_id))
    await session.execute(delete(SavedSignal).where(SavedSignal.signal_id == signal_id))
    await session.execute(delete(IgnoredSignal).where(IgnoredSignal.signal_id == signal_id))
    await session.execute(delete(RadarSignal).where(RadarSignal.signal_id == signal_id))
    await session.execute(delete(SignalTag).where(SignalTag.signal_id == signal_id))
    await session.execute(
        SourceEvent.__table__.update().where(SourceEvent.signal_id == signal_id).values(signal_id=None)
    )

    await session.delete(signal)
    await session.commit()


async def _get_signal(session: SessionDep, signal_id: str) -> Signal:
    signal = (
        await session.execute(select(Signal).where(Signal.id == signal_id))
    ).scalar_one_or_none()
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    return signal


saved_router = APIRouter(prefix="/saved", tags=["saved"])


@saved_router.get("", response_model=list[SignalOut])
async def list_saved(session: SessionDep, user: CurrentUser):
    signals = (
        (
            await session.execute(
                select(Signal)
                .join(SavedSignal, SavedSignal.signal_id == Signal.id)
                .where(SavedSignal.user_id == user.id)
                .order_by(SavedSignal.created_at.desc())
            )
        )
        .scalars()
        .unique()
        .all()
    )
    saved_ids, ignored_ids = await _user_sets(
        session, user.id, [s.id for s in signals]
    )
    return _apply_user_flags(list(signals), saved_ids, ignored_ids)
