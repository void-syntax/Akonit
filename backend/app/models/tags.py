"""Tags, aliases, custom tags and signal-tag links."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import uuid_str, utcnow


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    emoji: Mapped[str | None] = mapped_column(String(8))
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)

    aliases: Mapped[list["TagAlias"]] = relationship(
        back_populates="tag", cascade="all, delete-orphan"
    )
    signal_links: Mapped[list["SignalTag"]] = relationship(
        back_populates="tag", cascade="all, delete-orphan"
    )


class TagAlias(Base):
    __tablename__ = "tag_aliases"
    __table_args__ = (UniqueConstraint("tag_id", "alias"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tag_id: Mapped[str] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), index=True
    )
    alias: Mapped[str] = mapped_column(String(200))
    normalized: Mapped[str] = mapped_column(String(200), index=True)

    tag: Mapped[Tag] = relationship(back_populates="aliases")


class CustomTag(Base):
    __tablename__ = "custom_tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(140), index=True)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    hashtags: Mapped[list] = mapped_column(JSON, default=list)
    country_codes: Mapped[list] = mapped_column(JSON, default=list)
    source_ids: Mapped[list] = mapped_column(JSON, default=list)
    excludes: Mapped[list] = mapped_column(JSON, default=list)
    emoji: Mapped[str | None] = mapped_column(String(8))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SignalTag(Base):
    __tablename__ = "signal_tags"
    __table_args__ = (UniqueConstraint("signal_id", "tag_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    signal_id: Mapped[str] = mapped_column(
        ForeignKey("signals.id", ondelete="CASCADE"), index=True
    )
    tag_id: Mapped[str] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), index=True
    )
    matched_by: Mapped[str | None] = mapped_column(String(40))
    score: Mapped[float] = mapped_column(Float, default=0.0)

    signal: Mapped["Signal"] = relationship(back_populates="tag_links")  # noqa: F821
    tag: Mapped[Tag] = relationship(back_populates="signal_links")