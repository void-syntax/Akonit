"""SQLAlchemy engine/session. Works with Postgres, and SQLite for local dev."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from app.core.config import settings


class Base(DeclarativeBase):
    type_annotation_map: dict[Any, Any] = {}


def _build_engine(url: str) -> AsyncEngine:
    echo = settings.api_debug and settings.db_echo
    if url.startswith("sqlite"):
        return create_async_engine(
            url,
            echo=echo,
            future=True,
            poolclass=StaticPool,
            connect_args={
                "check_same_thread": False,
                "timeout": 30,
            },
        )
    return create_async_engine(
        url,
        echo=echo,
        future=True,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )


engine: AsyncEngine = _build_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_models() -> None:
    """Create tables directly (used for SQLite dev mode; Alembic owns Postgres)."""
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)