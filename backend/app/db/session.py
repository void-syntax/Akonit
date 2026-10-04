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
            connect_args={"check_same_thread": False},
        )
    return create_async_engine(
        url,
        echo=echo,
        future=True,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )


async def _resolve_database_url() -> str:
    """Try DATABASE_URL, then the explicit fallback if one is configured.

    The fallback exists for developer machines that cannot resolve the database
    host. It is never used silently: a warning is logged, and production simply
    leaves DATABASE_URL_FALLBACK empty so a bad host fails loudly.
    """
    primary = settings.database_url

    if primary.startswith("sqlite") or not settings.database_url_fallback:
        return primary

    import asyncio

    from app.core.logging import get_logger

    logger = get_logger(__name__)

    probe = _build_engine(primary)
    try:
        await asyncio.wait_for(
            probe.connect(), timeout=settings.db_probe_timeout_seconds
        )
        return primary
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "cannot reach %s (%s); using DATABASE_URL_FALLBACK",
            primary.rsplit("@", 1)[-1],
            type(exc).__name__,
        )
        return settings.database_url_fallback
    finally:
        await probe.dispose()


async def create_engine() -> AsyncEngine:
    """Build the engine after resolving which URL is actually usable."""
    return _build_engine(await _resolve_database_url())


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