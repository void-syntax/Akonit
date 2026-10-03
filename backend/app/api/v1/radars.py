"""Radar CRUD + matching endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    Radar,
    RadarCondition,
    RadarConditionGroup,
    RadarSignal,
    Signal,
)
from app.models.enums import SignalStatus
from app.radar.ast import Group, normalize_ast, summarize_conditions
from app.schemas.api import RadarCreate, RadarOut, RadarUpdate, SignalOut
from app.services.radar_service import (
    RadarView,
    _persist_conditions,
    create_radar,
    groups_to_ast,
    match_signal_to_radars,
)

router = APIRouter(prefix="/radars", tags=["radars"])


async def _load_radar(session: SessionDep, user_id: str, radar_id: str) -> Radar:
    radar = (
        await session.execute(
            select(Radar).where(Radar.id == radar_id, Radar.user_id == user_id)
        )
    ).scalar_one_or_none()
    if radar is None:
        raise HTTPException(status_code=404, detail="Radar not found")
    return radar


def _signal_out(signal: Signal) -> SignalOut:
    return SignalOut(
        **{
            f: getattr(signal, f)
            for f in SignalOut.model_fields
            if hasattr(signal, f)
        }
    )


async def _active_signal_count(session: SessionDep, radar_id: str) -> int:
    count = (
        await session.execute(
            select(func.count())
            .select_from(RadarSignal)
            .join(Signal, Signal.id == RadarSignal.signal_id)
            .where(
                RadarSignal.radar_id == radar_id,
                RadarSignal.is_dismissed.is_(False),
                Signal.status != SignalStatus.FADING,
            )
        )
    ).scalar_one()
    return int(count)


def _to_out(radar: Radar, active_count: int = 0) -> RadarOut:
    return RadarOut(
        id=radar.id,
        name=radar.name,
        emoji=radar.emoji,
        description=radar.description,
        countries=radar.countries or [],
        source_ids=radar.source_ids or [],
        tag_slugs=radar.tag_slugs or [],
        signal_threshold=radar.signal_threshold,
        notification_frequency=radar.notification_frequency,
        notification_channels=radar.notification_channels or [],
        is_active=radar.is_active,
        match_count=radar.match_count,
        active_signal_count=active_count,
        last_matched_at=radar.last_matched_at,
        created_at=radar.created_at,
    )


@router.get("", response_model=list[RadarOut])
async def list_radars(session: SessionDep, user: CurrentUser):
    radars = (
        (
            await session.execute(
                select(Radar)
                .where(Radar.user_id == user.id)
                .order_by(Radar.created_at.desc())
            )
        )
        .scalars()
        .unique()
        .all()
    )
    return [
        _to_out(radar, await _active_signal_count(session, radar.id))
        for radar in radars
    ]


@router.post("", response_model=RadarOut, status_code=status.HTTP_201_CREATED)
async def create(payload: RadarCreate, session: SessionDep, user: CurrentUser):
    radar = await create_radar(
        session,
        user_id=user.id,
        name=payload.name,
        emoji=payload.emoji,
        description=payload.description,
        conditions=payload.conditions,
        signal_threshold=payload.signal_threshold,
        notification_frequency=payload.notification_frequency,
        notification_channels=payload.notification_channels,
    )
    return _to_out(radar)


@router.get("/{radar_id}", response_model=RadarOut)
async def get_radar(radar_id: str, session: SessionDep, user: CurrentUser):
    radar = await _load_radar(session, user.id, radar_id)
    return _to_out(radar, await _active_signal_count(session, radar.id))


async def _replace_conditions(session: SessionDep, radar_id: str, root) -> None:
    groups = (
        (
            await session.execute(
                select(RadarConditionGroup).where(
                    RadarConditionGroup.radar_id == radar_id
                )
            )
        )
        .scalars()
        .unique()
        .all()
    )
    for group in groups:
        await session.delete(group)
    await session.flush()
    await _persist_conditions(session, radar_id, root)


@router.patch("/{radar_id}", response_model=RadarOut)
async def update(
    radar_id: str, payload: RadarUpdate, session: SessionDep, user: CurrentUser
):
    radar = await _load_radar(session, user.id, radar_id)
    data = payload.model_dump(exclude_none=True)

    for field in (
        "name",
        "emoji",
        "description",
        "signal_threshold",
        "notification_frequency",
        "notification_channels",
        "is_active",
    ):
        if field in data:
            setattr(radar, field, data[field])

    if "conditions" in data:
        root = normalize_ast(data["conditions"])
        summary = summarize_conditions(root)
@router.get("/{radar_id}/conditions")
async def get_conditions(radar_id: str, session: SessionDep, user: CurrentUser):
    """Return the AST rebuilt from the relational tables."""
    radar = await _load_radar(session, user.id, radar_id)
    groups = (
        (
            await session.execute(
                select(RadarConditionGroup)
                .where(RadarConditionGroup.radar_id == radar.id)
                .options(selectinload(RadarConditionGroup.conditions))
                .order_by(RadarConditionGroup.position)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    ast = groups_to_ast(list(groups))
    return {
        "radar_id": radar.id,
        "ast": _ast_to_dict(ast),
        "threshold": radar.signal_threshold,
    }


def _ast_to_dict(group: Group) -> dict:
    """Serialise the AST back to the plain JSON shape the UI understands."""
    children: list[dict] = []
    for child in group.children:
        if child.is_group and child.group is not None:
            children.append(_ast_to_dict(child.group))
        elif child.condition is not None:
            cond = child.condition
            children.append(
                {
                    "type": getattr(cond.type, "value", cond.type),
                    "operator": getattr(cond.operator, "value", cond.operator),
                    "value": cond.value,
                    "unit": getattr(cond, "unit", None),
                }
            )
    return {
        "op": group.op,
        "children": children,
        "is_exclude": group.is_exclude,
    }


@router.get("/{radar_id}/signals", response_model=list[SignalOut])
async def radar_signals(
    radar_id: str, session: SessionDep, user: CurrentUser, limit: int = 50
):
    radar = await _load_radar(session, user.id, radar_id)
    signals = (
        (
            await session.execute(
                select(Signal)
                .join(RadarSignal, RadarSignal.signal_id == Signal.id)
                .where(RadarSignal.radar_id == radar.id)
                .order_by(Signal.strength.desc())
                .limit(limit)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    return [_signal_out(s) for s in signals]


@router.post("/{radar_id}/run")
async def run_now(radar_id: str, session: SessionDep, user: CurrentUser):
    """Re-evaluate recent signals against this radar immediately."""
    radar = await _load_radar(session, user.id, radar_id)
    since = datetime.now(UTC) - timedelta(hours=6)
    signals = (
        (
            await session.execute(
                select(Signal)
                .where(Signal.first_seen_at >= since)
                .order_by(Signal.strength.desc())
                .limit(200)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    matched = 0
    for signal in signals:
        outcomes = await match_signal_to_radars(session, signal, user_ids=[user.id])
        matched += sum(1 for o in outcomes if o.radar_id == radar.id)
    return {"radar_id": radar.id, "evaluated": len(signals), "matched": matched}


@router.post("/preview")
async def preview_conditions(payload: dict, session: SessionDep, user: CurrentUser):
    """Dry-run: which newest signals would this condition set match?"""
    from app.radar.evaluator import evaluate_group

    root = normalize_ast(payload.get("conditions"))
    limit = int(payload.get("limit", 20))
    signals = (
        (
            await session.execute(
                select(Signal).order_by(Signal.strength.desc()).limit(200)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    hits = [
        _signal_out(s) for s in signals if evaluate_group(root, RadarView(s))
    ]
    return {"matched": len(hits), "items": hits[:limit]}
