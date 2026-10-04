"""Condition AST shared by the API, the UI and the evaluator.

    {"op": "AND", "children": [
        {"op": "OR", "children": [
            {"type": "country", "operator": "IN", "value": ["KR", "JP"]},
            {"type": "source",  "operator": "IN", "value": ["tiktok"]},
        ]},
        {"type": "growth", "operator": "GT", "value": 100},
        {"op": "NOT", "children": [
            {"type": "tag", "operator": "IN", "value": ["cosplay"]},
        ]},
    ]}
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import ConditionOperator, ConditionType, JoinType


class Condition(BaseModel):
    """A leaf condition such as Country IN [KR, JP]."""

    type: ConditionType
    operator: ConditionOperator = ConditionOperator.IN
    value: Any = None
    unit: str | None = None

    @field_validator("value")
    @classmethod
    def _coerce(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, (str, int, float, bool)):
            return v
        if isinstance(v, (list, tuple, set)):
            return [str(x) for x in v]
        return v


class Node:
    """Either a group or a leaf condition.

    A plain class on purpose: it accepts pydantic Conditions, DB row adapters
    and Groups without re-validation, which keeps the engine fast and the
    callers simple.
    """

    __slots__ = ("group", "condition")

    def __init__(self, group: Any = None, condition: Any = None) -> None:
        self.group = group
        self.condition = condition

    @classmethod
    def build(cls, child: Any) -> "Node":
        if isinstance(child, Node):
            return child
        if hasattr(child, "op") and hasattr(child, "children"):
            return cls(group=child)
        return cls(condition=child)

    @property
    def is_group(self) -> bool:
        return self.group is not None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Node(group={self.group!r}, condition={self.condition!r})"


class Group(BaseModel):
    """A boolean node: AND / OR / NOT."""

    op: Literal["AND", "OR", "NOT"] = "AND"
    children: list[Any] = Field(default_factory=list)
    is_exclude: bool = False

    @field_validator("children", mode="before")
    @classmethod
    def _wrap(cls, value: Any) -> Any:
        """Accept Groups and Conditions directly inside children."""
        if not isinstance(value, (list, tuple)):
            return value
        return [Node.build(item) for item in value]

    def __init__(self, op: str = "AND", children: list[Any] | None = None, **kw):
        super().__init__(op=op, children=children or [], **kw)


def make_node(child: Any) -> Node:
    return Node.build(child)


def normalize_ast(payload: dict[str, Any] | list[dict[str, Any]] | None) -> Group:
    """Accept the frontend shape and return a root Group.

    Both forms are supported:
      {"op": "AND", "children": [...]}          (explicit root)
      [{"type": "country", ...}, ...]            (flat list of conditions)
    """
    if not payload:
        return Group(op="AND", children=[])

    if isinstance(payload, list):
        return Group(op="AND", children=[_node(c) for c in payload])

    root = payload
    if "op" in root or "children" in root:
        return _group_from_dict(root)
    return Group(op="AND", children=[_node(root)])


def _group_from_dict(data: dict[str, Any]) -> Group:
    children = [
        _group_from_dict(c) if ("op" in c or "children" in c) else Node(
            condition=Condition.model_validate(c)
        )
        for c in data.get("children") or []
    ]
    return Group(
        op=data.get("op", "AND"),
        children=children,
        is_exclude=bool(data.get("is_exclude", False)),
    )


def _node(item: dict[str, Any]) -> Node:
    if "op" in item or "children" in item:
        return Node(group=_group_from_dict(item))
    return Node(condition=Condition.model_validate(item))


def ast_to_groups(root: Group) -> list[dict[str, Any]]:
    """Flatten to the radar_condition_groups / radar_conditions tables."""
    rows: list[dict[str, Any]] = []

    def walk(group: Group, position: int) -> None:
        group_id = f"g{position}"
        rows.append(
            {
                "id": group_id,
                "position": position,
                "join_type": JoinType[group.op],
                "is_exclude": group.is_exclude,
                "conditions": [],
            }
        )
        cond_position = 0
        for child in group.children:
            if child.is_group and child.group is not None:
                walk(child.group, position * 10 + len(rows) % 10)
            elif child.condition is not None:
                cond = child.condition
                rows[-1]["conditions"].append(
                    {
                        "position": cond_position,
                        "type": cond.type,
                        "operator": cond.operator,
                        "value_json": cond.value if cond.value is not None else {},
                        "value_num": cond.value
                        if isinstance(cond.value, (int, float))
                        else None,
                        "unit": cond.unit,
                    }
                )
                cond_position += 1

    walk(root, 0)
    return rows


def summarize_conditions(root: Group) -> dict[str, list[str]]:
    """Denormalised summary shown on radar cards.

    Walks the whole tree: the previous version only looked two levels deep, so
    a condition nested inside two or more groups was silently dropped from the
    summary and any pre-filter built on it excluded valid signals.
    """
    summary: dict[str, list[str]] = {
        "countries": [],
        "sources": [],
        "tags": [],
        "keywords": [],
        "excludes": [],
    }

    def walk(group: Group) -> None:
        for child in group.children:
            if child.is_group and child.group is not None:
                walk(child.group)
            else:
                _collect(child.condition, summary)

    walk(root)
    return summary


def _collect(condition: Condition | None, summary: dict[str, list[str]]) -> None:
    if condition is None:
        return
    bucket = {
        ConditionType.COUNTRY: "countries",
        ConditionType.SOURCE: "sources",
        ConditionType.TAG: "tags",
        ConditionType.KEYWORD: "keywords",
    }.get(condition.type)
    if bucket is None:
        return
    values = condition.value if isinstance(condition.value, list) else [condition.value]
    for value in values:
        if value is None:
            continue
        if condition.operator == ConditionOperator.NOT_IN:
            summary["excludes"].append(str(value))
        elif str(value) not in summary[bucket]:
            summary[bucket].append(str(value))