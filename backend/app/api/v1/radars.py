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
    cond_value,
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
        # The denormalised columns are what the feed and radar cards filter on,
        # so they must be refreshed whenever the tree changes.
        radar.countries = summary.countries
        radar.source_ids = summary.source_ids
        radar.tag_slugs = summary.tag_slugs
        await _replace_conditions(session, radar.id, root)

    await session.commit()
    await session.refresh(radar)
    return _to_out(radar, await _active_signal_count(session, radar.id))


@router.delete("/{radar_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_radar(
    radar_id: str, session: SessionDep, user: CurrentUser
):
    radar = await _load_radar(session, user.id, radar_id)
    await session.delete(radar)
    await session.commit()
    return None


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


@router.get("/{radar_id}/summary", response_model=dict)
async def radar_summary(radar_id: str, session: SessionDep, user: CurrentUser):
    """Human-readable conditions, e.g. 'South Korea + TikTok + Growth > 100%'."""
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
    return {
        "radar_id": radar.id,
        "parts": summarize_radar(groups),
        "threshold": radar.signal_threshold,
        "frequency": radar.notification_frequency.value,
    }


COUNTRY_NAMES: dict[str, str] = {
    "KR": "South Korea", "JP": "Japan", "US": "United States",
    "GB": "United Kingdom", "CN": "China", "TR": "Turkey",
    "AE": "UAE", "AZ": "Azerbaijan", "BR": "Brazil", "IN": "India",
    "DE": "Germany", "FR": "France", "ES": "Spain", "IT": "Italy",
    "MX": "Mexico", "CA": "Canada", "AU": "Australia", "RU": "Russia",
}

SOURCE_NAMES: dict[str, str] = {
    "tiktok": "TikTok", "youtube": "YouTube", "instagram": "Instagram",
    "x_trends": "X", "reddit": "Reddit", "google_trends": "Google Trends",
    "google_news_trends": "Google News", "github": "GitHub",
    "huggingface": "Hugging Face", "producthunt": "Product Hunt",
    "hackernews": "Hacker News", "npm": "npm", "devto": "DEV",
    "lobsters": "Lobsters", "stackoverflow": "Stack Overflow",
}

OPERATOR_TEXT = {
    "GT": ">", "GTE": "≥", "LT": "<", "LTE": "≤",
    "IN": "is", "NOT_IN": "is not", "EQ": "=", "CONTAINS": "contains",
}


def summarize_radar(groups) -> list[str]:
    """Turn condition rows into plain sentences the UI can render directly."""
    parts: list[str] = []
    tag_names: list[str] = []

    for group in groups:
        pieces: list[str] = []
        for cond in group.conditions:
            value = cond_value(cond)
            kind = cond.condition_type.value
            operator = OPERATOR_TEXT.get(cond.operator.value, cond.operator.value)

            if kind == "COUNTRY":
                codes = [str(c).upper() for c in value] if isinstance(value, list) else [str(value).upper()]
                labels = [COUNTRY_NAMES.get(c, c) for c in codes]
                pieces.append(f"{'Country' if cond.operator.value != 'NOT_IN' else 'Not country'} {' / '.join(labels)}")
            elif kind == "SOURCE":
                ids = value if isinstance(value, list) else [value]
                labels = [SOURCE_NAMES.get(str(s), str(s)) for s in ids]
                pieces.append(f"{'Source' if cond.operator.value != 'NOT_IN' else 'Not source'} {' / '.join(labels)}")
            elif kind == "TAG":
                names = value if isinstance(value, list) else [value]
                pretty = " / ".join(str(n).replace("-", " ").title() for n in names)
                if cond.operator.value == "NOT_IN":
                    pieces.append(f"Exclude {pretty}")
                else:
                    tag_names.extend(str(n) for n in names)
            elif kind == "GROWTH":
                pieces.append(f"Growth {operator} {round(float(value or 0))}%")
            elif kind == "STRENGTH":
                pieces.append(f"Strength {operator} {round(float(value or 0))}")
            elif kind == "ACTIVITY":
                pieces.append(f"Activity {operator} {int(float(value or 0))}")
            elif kind == "AGE":
                unit = (cond.unit or "minutes").rstrip("s")
                pieces.append(f"Age {operator} {round(float(value or 0))} {unit}")
            elif kind == "STATUS":
                names = value if isinstance(value, list) else [value]
                pieces.append("Status " + " / ".join(str(n).title() for n in names))
            elif kind == "KEYWORD":
                words = value if isinstance(value, list) else [value]
                pieces.append(f"{'Exclude' if cond.operator.value == 'NOT_IN' else 'Keyword'} {' / '.join(str(w) for w in words)}")

        if not pieces:
            continue
        joiner = " + " if group.join_type.value == "AND" else " or "
        text = joiner.join(pieces)
        parts.append(f"NOT ({text})" if group.is_exclude else text)

    if tag_names:
        parts.insert(0, "Tags " + " / ".join(tag_names))
    if not parts:
        parts.append("All signals")
    return parts


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
