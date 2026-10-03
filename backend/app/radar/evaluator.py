"""Condition evaluator — runs the AST against a signal.

This is the pure, synchronous core used both for the live check on newly
detected signals and for the batch pre-filter query.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.models.enums import ConditionOperator, ConditionType, SignalStatus
from app.radar.ast import Condition, Group

UNIT_SECONDS = {
    "minutes": 60,
    "minute": 60,
    "hours": 3600,
    "hour": 3600,
    "days": 86400,
    "day": 86400,
    "weeks": 604800,
    "week": 604800,
}


class SignalLike(Protocol):
    title: str
    description: str
    category: str | None
    hashtags: list
    country_code: str | None
    source_id: str
    source_url: str
    growth: float
    current_activity: float
    strength: float
    status: str
    first_seen_at: datetime
    tag_slugs: set[str]
    keywords: list[str]


def evaluate_group(group: Group | None, signal: SignalLike) -> bool:
    if group is None or not group.children:
        return True

    results = [
        evaluate_group(child.group, signal)
        if child.is_group
        else evaluate(child.condition, signal)  # type: ignore[arg-type]
        for child in group.children
    ]

    if group.op == "AND":
        value = all(results)
    elif group.op == "OR":
        value = any(results)
    else:  # NOT
        value = not all(results)

    return (not value) if group.is_exclude else value


def evaluate(condition: Condition, signal: SignalLike) -> bool:
    op = condition.operator
    value = condition.value

    if condition.type == ConditionType.COUNTRY:
        target = (signal.country_code or "GLOBAL").upper()
        candidates = _as_list(value)
        if condition.unit == "all" or value == "ALL":
            return True
        return _compare_membership(target, candidates, op)

    if condition.type == ConditionType.SOURCE:
        candidates = _as_list(value)
        if condition.unit == "all" or value == "ALL":
            return True
        return _compare_membership(signal.source_id, candidates, op)

    if condition.type == ConditionType.TAG:
        candidates = {c.lower() for c in _as_list(value)}
        if not candidates:
            return True
        hit = bool(candidates & signal.tag_slugs)
        return hit if op in (ConditionOperator.IN, ConditionOperator.CONTAINS) else not hit

    if condition.type == ConditionType.KEYWORD:
        haystack = f"{signal.title} {signal.description}".lower()
        keywords = [str(k).lower() for k in _as_list(value)]
        if not keywords:
            return True
        if op == ConditionOperator.NOT_IN:
            return not any(k in haystack for k in keywords)
        return any(k in haystack for k in keywords)

    if condition.type == ConditionType.GROWTH:
        return _compare_numeric(signal.growth, value, op)

    if condition.type == ConditionType.ACTIVITY:
        return _compare_numeric(signal.current_activity, value, op)

    if condition.type == ConditionType.STRENGTH:
        return _compare_numeric(signal.strength, value, op)

    if condition.type == ConditionType.AGE:
        age_minutes = age_in_minutes(signal.first_seen_at)
        unit = (condition.unit or "minutes").lower()
        limit = float(value or 0) * (UNIT_SECONDS.get(unit, 60) / 60)
        return _compare_numeric(age_minutes, limit, op)

    if condition.type == ConditionType.STATUS:
        candidates = {str(s).upper() for s in _as_list(value)}
        if not candidates:
            return True
        current = str(signal.status).upper()
        if op == ConditionOperator.NOT_IN:
            return current not in candidates
        return current in candidates

    return True


def age_in_minutes(first_seen_at: datetime | None) -> float:
    if first_seen_at is None:
        return 0.0
    if first_seen_at.tzinfo is None:
        first_seen_at = first_seen_at.replace(tzinfo=UTC)
    return max((datetime.now(UTC) - first_seen_at).total_seconds() / 60, 0.0)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _compare_membership(
    target: str, candidates: list[Any], op: ConditionOperator
) -> bool:
    normalized = {str(c).upper() for c in candidates}
    if op == ConditionOperator.NOT_IN:
        return target.upper() not in normalized
    return target.upper() in normalized


def _compare_numeric(
    left: float, value: Any, op: ConditionOperator
) -> bool:
    try:
        right = float(value)
    except (TypeError, ValueError):
        return True
    if op == ConditionOperator.GT:
        return left > right
    if op == ConditionOperator.GTE:
        return left >= right
    if op == ConditionOperator.LT:
        return left < right
    if op == ConditionOperator.LTE:
        return left <= right
    if op == ConditionOperator.EQ:
        return abs(left - right) < 1e-6
    if op == ConditionOperator.NOT_IN:
        return left != right
    return True


def status_values() -> list[str]:
    return [s.value for s in SignalStatus]


def within_age(first_seen_at: datetime, minutes: float) -> bool:
    return age_in_minutes(first_seen_at) <= minutes


def hours_ago(hours: float) -> datetime:
    return datetime.now(UTC) - timedelta(hours=hours)