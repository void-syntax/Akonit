"""Signals and their immutable activity history."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import SignalStatus, uuid_str, utcnow


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        Index("ix_signals_status_strength", "status", "strength"),
        Index("ix_signals_country_status", "country_code", "status"),
        Index("ix_signals_first_seen", "first_seen_at"),
        Index("ix_signals_source_status", "source_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    cluster_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    title: Mapped[str] = mapped_column(String(500))
    slug: Mapped[str] = mapped_column(String(520), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str | None] = mapped_column(String(80), index=True)
    hashtags: Mapped[list] = mapped_column(JSON, default=list)
    country_code: Mapped[str | None] = mapped_column(String(2), index=True)
    country_name: Mapped[str | None] = mapped_column(String(120))
    flag: Mapped[str | None] = mapped_column(String(16))

    source_id: Mapped[str] = mapped_column(String(40), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    thumbnail: Mapped[str | None] = mapped_column(Text)
    cross_source_count: Mapped[int] = mapped_column(Integer, default=1)
    cross_source_urls: Mapped[list] = mapped_column(JSON, default=list)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    current_activity: Mapped[float] = mapped_column(Float, default=0.0)
    previous_activity: Mapped[float] = mapped_column(Float, default=0.0)
    growth: Mapped[float] = mapped_column(Float, default=0.0)
    acceleration: Mapped[float] = mapped_column(Float, default=0.0)

    status: Mapped[SignalStatus] = mapped_column(
        SAEnum(SignalStatus), default=SignalStatus.NEW, index=True
    )
    strength: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    age_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    activity_metric: Mapped[str | None] = mapped_column(String(40))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    topics: Mapped[list] = mapped_column(JSON, default=list)
    keywords: Mapped[list] = mapped_column(JSON, default=list)

    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    # --- radar engine support ---
    velocity: Mapped[float] = mapped_column(Float, default=0.0)
    """Smoothed rate of change. Far more stable than raw growth between two
    adjacent collection windows, which is what a real trend looks like."""

    density_count: Mapped[int] = mapped_column(Integer, default=1)
    """How many recent signals share this signal's strongest tag (a burst)."""

    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """Last time this signal was evaluated against any radar."""

    tags_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    tag_links: Mapped[list["SignalTag"]] = relationship(  # noqa: F821
        back_populates="signal", cascade="all, delete-orphan"
    )
    snapshots: Mapped[list["SignalSnapshot"]] = relationship(
        back_populates="signal",
        cascade="all, delete-orphan",
        order_by="SignalSnapshot.captured_at",
    )
    radar_matches: Mapped[list["RadarSignal"]] = relationship(  # noqa: F821
        back_populates="signal", cascade="all, delete-orphan"
    )


class SignalSnapshot(Base):
    """Historical activity points — appended, never overwritten."""

    __tablename__ = "signal_snapshots"
    __table_args__ = (Index("ix_snapshots_signal_time", "signal_id", "captured_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    signal_id: Mapped[str] = mapped_column(
        ForeignKey("signals.id", ondelete="CASCADE"), index=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    activity: Mapped[float] = mapped_column(Float, default=0.0)
    previous_activity: Mapped[float] = mapped_column(Float, default=0.0)
    growth: Mapped[float] = mapped_column(Float, default=0.0)
    acceleration: Mapped[float] = mapped_column(Float, default=0.0)
    strength: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[SignalStatus] = mapped_column(
        SAEnum(SignalStatus), default=SignalStatus.NEW
    )
    rank: Mapped[int | None] = mapped_column(Integer)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)

    signal: Mapped[Signal] = relationship(back_populates="snapshots")