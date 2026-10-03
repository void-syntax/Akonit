"""Countries, sources and raw source events."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
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
from app.models.enums import SourceStatus, SourceType, uuid_str, utcnow


class Country(Base):
    __tablename__ = "countries"

    code: Mapped[str] = mapped_column(String(2), primary_key=True)
    alpha3: Mapped[str] = mapped_column(String(3))
    name: Mapped[str] = mapped_column(String(120), index=True)
    slug: Mapped[str] = mapped_column(String(120), index=True)
    flag: Mapped[str] = mapped_column(String(16))
    region: Mapped[str | None] = mapped_column(String(80))
    is_supported: Mapped[bool] = mapped_column(Boolean, default=False)


class Source(Base):
    """Auto-registered by the Source Registry at worker startup."""

    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    type: Mapped[SourceType] = mapped_column(SAEnum(SourceType))
    adapter: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[SourceStatus] = mapped_column(
        SAEnum(SourceStatus), default=SourceStatus.ACTIVE
    )
    cost: Mapped[str] = mapped_column(String(32), default="FREE")
    credentials_required: Mapped[bool] = mapped_column(Boolean, default=False)
    status_reason: Mapped[str | None] = mapped_column(Text)
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    collect_interval_seconds: Mapped[int] = mapped_column(Integer, default=900)

    last_fetch: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    records_fetched: Mapped[int] = mapped_column(Integer, default=0)
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    rate_limit_remaining: Mapped[int | None] = mapped_column(Integer)
    rate_limit_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    strategy: Mapped[str | None] = mapped_column(String(120))
    extra: Mapped[dict] = mapped_column(JSON, default=dict)

    events: Mapped[list["SourceEvent"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class SourceEvent(Base):
    """Raw collector output, stored before normalization for auditability."""

    __tablename__ = "source_events"
    __table_args__ = (Index("ix_source_events_src_time", "source_id", "fetched_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(300), index=True)
    raw_url: Mapped[str | None] = mapped_column(Text)
    raw_title: Mapped[str | None] = mapped_column(Text)
    raw_activity: Mapped[float] = mapped_column(Float, default=0.0)
    activity_metric: Mapped[str | None] = mapped_column(String(40))
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    cluster_id: Mapped[str | None] = mapped_column(String(64), index=True)
    country_code: Mapped[str | None] = mapped_column(String(2))
    rank: Mapped[int | None] = mapped_column(Integer)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    normalized: Mapped[bool] = mapped_column(Boolean, default=False)
    signal_id: Mapped[str | None] = mapped_column(
        ForeignKey("signals.id", ondelete="SET NULL"), index=True
    )

    source: Mapped[Source] = relationship(back_populates="events")