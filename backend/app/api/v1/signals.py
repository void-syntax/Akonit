"""Signal feed, detail and history endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, OptionalUser, SessionDep
from app.models import (
    IgnoredSignal,
    Radar,
    RadarSignal,
    SavedSignal,
    Signal,
    SignalSnapshot,
)
from app.models.enums import SignalStatus
from app.schemas.api import SignalDetail, SignalOut, SignalPage

router = APIRouter(prefix="/signals", tags=["signals"])


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
    """Public feed. Signed-in visitors additionally get saved/ignored flags."""
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
            return SignalPage(items=[], total=0, limit=limit, offset=offset)
        statement = statement.join(
            SavedSignal, SavedSignal.signal_id == Signal.id
        ).where(SavedSignal.user_id == user.id)

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

    # Tags are filtered in SQL, not in Python. Filtering after the query meant
    # `total` counted every signal regardless of the tag filter, and pagination
    # silently returned short pages once a tag was selected.
    #
    # A LIKE over the serialised JSON is used deliberately instead of
    # json_each/jsonb_array_elements: it renders identically on Postgres and
    # SQLite, needs no dialect-specific lateral join, and cannot produce a
    # duplicate row per matching tag. The value is a quoted JSON string, so a
    # needle of '"tag"' cannot match inside a longer tag name.
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
                    Signal.strength.desc(), Signal.first_seen_at.desc()
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

    return SignalPage(
        items=_apply_user_flags(list(rows), saved_ids, ignored_ids),
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{signal_id}", response_model=SignalDetail)
async def signal_detail(signal_id: str, session: SessionDep, user: OptionalUser):
    signal = (
        (
            await session.execute(
                select(Signal)
                .where(Signal.id == signal_id)
                .options(selectinload(Signal.snapshots))
            )
        )
        .scalar_one_or_none()
    )
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")

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
            for s in signal.snapshots
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
