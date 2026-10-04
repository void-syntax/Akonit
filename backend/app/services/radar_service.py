"""Radar service: condition engine wiring plus matching against new signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models import (
    CustomTag,
    Radar,
    RadarCondition,
    RadarConditionGroup,
    RadarSignal,
    Signal,
)
from app.models.enums import (
    ConditionOperator,
    ConditionType,
    JoinType,
    NotificationFrequency,
    SignalStatus,
)
from app.radar.ast import Group, Node, normalize_ast, summarize_conditions
from app.radar.evaluator import evaluate_group

logger = get_logger(__name__)


class RadarView:
    """Adapts a Signal row to what the evaluator expects."""

    __slots__ = (
        "title",
        "description",
        "category",
        "hashtags",
        "country_code",
        "source_id",
        "source_url",
        "growth",
        "current_activity",
        "strength",
        "status",
        "first_seen_at",
        "tag_slugs",
        "keywords",
    )

    def __init__(self, signal: Signal) -> None:
        self.title = signal.title
        self.description = signal.description or ""
        self.category = signal.category
        self.hashtags = signal.hashtags or []
        self.country_code = signal.country_code
        self.source_id = signal.source_id
        self.source_url = signal.source_url
        self.growth = signal.growth
        self.current_activity = signal.current_activity
        self.strength = signal.strength
        self.status = signal.status
        self.first_seen_at = signal.first_seen_at
        self.tag_slugs = set(signal.keywords or [])
        self.keywords = signal.keywords or []


@dataclass
class MatchOutcome:
    radar_id: str
    signal_id: str
    is_new: bool
    notify: bool = False
    reason: str = ""


class SimpleCondition:
    """A leaf condition rebuilt from a DB row."""

    __slots__ = ("type", "operator", "value", "unit")

    def __init__(
        self,
        condition_type: ConditionType,
        operator: ConditionOperator,
        value: Any,
        unit: str | None,
    ) -> None:
        self.type = condition_type
        self.operator = operator
        self.value = value
        self.unit = unit


def cond_value(cond: RadarCondition) -> Any:
    if cond.value_json:
        return cond.value_json
    if cond.value_num is not None:
        return cond.value_num
    return None


def groups_to_ast(groups: list[RadarConditionGroup]) -> Group:
    """Rebuild the boolean AST from the relational radar conditions."""
    if not groups:
        return Group(op="AND", children=[])

    children = []
    for group in groups:
        leaves = [
            Node(
                condition=SimpleCondition(
                    c.condition_type, c.operator, cond_value(c), c.unit
                )
            )
            for c in group.conditions
        ]
        children.append(
            Node(
                group=Group(
                    op=group.join_type.value,
                    children=leaves,
                    is_exclude=group.is_exclude,
                )
            )
        )
    return Group(op="AND", children=children)


async def radar_matches_signal(
    session: AsyncSession, radar: Radar, signal: Signal
) -> tuple[bool, str]:
    """Evaluate one radar's condition tree against one signal."""
    if not radar.is_active:
        return False, "radar_inactive"
    if signal.strength < radar.signal_threshold:
        return False, "below_threshold"

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
    view = RadarView(signal)

    if evaluate_group(ast, view):
        return True, "matched"
    return False, "conditions_not_met"


async def create_radar(
    session: AsyncSession,
    *,
    user_id: str,
    name: str,
    conditions: dict[str, Any] | list[dict[str, Any]],
    emoji: str | None = None,
    description: str | None = None,
    signal_threshold: float = 0.0,
    notification_frequency: NotificationFrequency = NotificationFrequency.INSTANT,
    notification_channels: list[str] | None = None,
) -> Radar:
    root = normalize_ast(conditions)
    summary = summarize_conditions(root)

    radar = Radar(
        user_id=user_id,
        name=name,
        emoji=emoji,
        description=description,
        countries=summary["countries"],
        source_ids=summary["sources"],
        tag_slugs=summary["tags"],
        signal_threshold=signal_threshold,
        notification_frequency=notification_frequency,
        notification_channels=notification_channels or ["WEB_PUSH"],
        is_active=True,
    )
    session.add(radar)
    await session.flush()
    await _persist_conditions(session, radar.id, root)
    await session.commit()
    return radar


async def _persist_conditions(
    session: AsyncSession, radar_id: str, root: Group
) -> None:
    """Write the AST into radar_condition_groups / radar_conditions."""
    pending: list[tuple[RadarConditionGroup, list[RadarCondition]]] = []
    position = 0

    def walk(group: Group) -> None:
        nonlocal position
        db_group = RadarConditionGroup(
            radar_id=radar_id,
            position=position,
            join_type=JoinType(group.op),
            is_exclude=group.is_exclude,
        )
        session.add(db_group)
        position += 1

        conditions: list[RadarCondition] = []
        for i, child in enumerate(group.children):
            if child.condition is not None:
                cond = child.condition
                conditions.append(
                    RadarCondition(
                        position=i,
                        condition_type=cond.type,
                        operator=cond.operator,
                        value_json=cond.value if cond.value is not None else {},
                        value_num=(
                            cond.value
                            if isinstance(cond.value, (int, float))
                            else None
                        ),
                        unit=cond.unit,
                    )
                )
            elif child.group is not None:
                walk(child.group)

        pending.append((db_group, conditions))

    walk(root)
    await session.flush()

    for db_group, conditions in pending:
        for cond in conditions:
            cond.group_id = db_group.id
            session.add(cond)
    await session.flush()


async def match_signal_to_radars(
    session: AsyncSession,
    signal: Signal,
    *,
    lookback_minutes: int = 60,
    user_ids: list[str] | None = None,
) -> list[MatchOutcome]:
    """Check one signal against every active radar that uses its source."""
    statement = select(Radar).where(Radar.is_active.is_(True))
    if user_ids:
        statement = statement.where(Radar.user_id.in_(user_ids))
    radars = (await session.execute(statement)).scalars().unique().all()

    existing = {
        (rs.radar_id, rs.signal_id)
        for rs in (
            (
                await session.execute(
                    select(RadarSignal).where(
                        RadarSignal.signal_id == signal.id
                    )
                )
            )
            .scalars()
            .all()
        )
    }

    outcomes: list[MatchOutcome] = []
    for radar in radars:
        # The pair matters: a signal already matched by radar A must still be
        # evaluated against radar B.
        if (radar.id, signal.id) in existing:
            continue
        matched, reason = await radar_matches_signal(session, radar, signal)
        if not matched:
            continue

        session.add(
            RadarSignal(radar_id=radar.id, signal_id=signal.id, matched_at=datetime.now(UTC))
        )
        radar.match_count += 1
        radar.last_matched_at = datetime.now(UTC)
        outcomes.append(
            MatchOutcome(
                radar_id=radar.id,
                signal_id=signal.id,
                is_new=True,
                notify=radar.notification_frequency != NotificationFrequency.OFF,
                reason=reason,
            )
        )
    await session.commit()
    return outcomes


async def match_batch(
    session: AsyncSession,
    *,
    lookback_minutes: int = 60,
) -> list[MatchOutcome]:
    """Re-evaluate signals that are new OR whose metrics changed recently.

    Only looking at first_seen_at would miss the most valuable case: a signal
    that was slow at first and only later started to take off. Those have an
    old first_seen_at but a fresh last_seen_at, so both windows are scanned.
    """
    now = datetime.now(UTC)
    since_new = now - timedelta(minutes=lookback_minutes)
    since_changed = now - timedelta(minutes=lookback_minutes)

    statement = (
        select(Signal)
        .where(
            (Signal.first_seen_at >= since_new)
            | (Signal.matched_at.is_(None))
            | (Signal.matched_at <= since_changed)
        )
        .where(Signal.status != SignalStatus.FADING)
        .order_by(Signal.first_seen_at.desc())
        .limit(500)
    )
    signals = (await session.execute(statement)).scalars().unique().all()

    outcomes: list[MatchOutcome] = []
    for signal in signals:
        outcomes.extend(await match_signal_to_radars(session, signal))
        signal.matched_at = now

    if signals:
        await session.commit()

    return outcomes
