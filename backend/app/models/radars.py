"""Radars, condition trees and radar-signal matches."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import (
    ConditionOperator,
    ConditionType,
    JoinType,
    NotificationFrequency,
    uuid_str,
    utcnow,
)


class Radar(Base):
    __tablename__ = "radars"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    emoji: Mapped[str | None] = mapped_column(String(8))
    description: Mapped[str | None] = mapped_column(Text)

    # Denormalised summary used for radar cards
    countries: Mapped[list] = mapped_column(JSON, default=list)
    source_ids: Mapped[list] = mapped_column(JSON, default=list)
    tag_slugs: Mapped[list] = mapped_column(JSON, default=list)

    signal_threshold: Mapped[float] = mapped_column(Float, default=0.0)
    notification_frequency: Mapped[NotificationFrequency] = mapped_column(
        SAEnum(NotificationFrequency), default=NotificationFrequency.INSTANT
    )
    notification_channels: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    last_matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    match_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped["User"] = relationship(back_populates="radars")  # noqa: F821
    condition_groups: Mapped[list["RadarConditionGroup"]] = relationship(
        back_populates="radar",
        cascade="all, delete-orphan",
        order_by="RadarConditionGroup.position",
    )
    signal_matches: Mapped[list["RadarSignal"]] = relationship(
        back_populates="radar", cascade="all, delete-orphan"
    )


class RadarConditionGroup(Base):
    """Conditions inside a group join by join_type; groups join by their own join_type."""

    __tablename__ = "radar_condition_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    radar_id: Mapped[str] = mapped_column(
        ForeignKey("radars.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    join_type: Mapped[JoinType] = mapped_column(SAEnum(JoinType), default=JoinType.AND)
    is_exclude: Mapped[bool] = mapped_column(Boolean, default=False)

    radar: Mapped[Radar] = relationship(back_populates="condition_groups")
    conditions: Mapped[list["RadarCondition"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="RadarCondition.position",
    )


class RadarCondition(Base):
    __tablename__ = "radar_conditions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    group_id: Mapped[str] = mapped_column(
        ForeignKey("radar_condition_groups.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    condition_type: Mapped[ConditionType] = mapped_column(SAEnum(ConditionType))
    operator: Mapped[ConditionOperator] = mapped_column(SAEnum(ConditionOperator))
    value_json: Mapped[dict] = mapped_column(JSON, default=dict)
    value_num: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(20))

    group: Mapped[RadarConditionGroup] = relationship(back_populates="conditions")


class RadarSignal(Base):
    __tablename__ = "radar_signals"
    __table_args__ = (UniqueConstraint("radar_id", "signal_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    radar_id: Mapped[str] = mapped_column(
        ForeignKey("radars.id", ondelete="CASCADE"), index=True
    )
    signal_id: Mapped[str] = mapped_column(
        ForeignKey("signals.id", ondelete="CASCADE"), index=True
    )
    matched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)

    radar: Mapped[Radar] = relationship(back_populates="signal_matches")
    signal: Mapped["Signal"] = relationship(back_populates="radar_matches")  # noqa: F821