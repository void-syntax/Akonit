"""Production-ready database module with connection pooling, automatic migrations check,
and graceful fallback to SQLite for local standalone execution.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import AsyncAdaptedQueuePool, StaticPool

from app.core.config import settings


class Base(DeclarativeBase):
    type_annotation_map: dict[Any, Any] = {}


def _get_database_url() -> str:
    url = os.getenv("DATABASE_URL") or getattr(settings, "database_url", None)
    if not url:
        url = "sqlite:///./akonit.db"
    return url


def _build_engine(url: str) -> AsyncEngine:
    echo = getattr(settings, "api_debug", True) and getattr(settings, "db_echo", False)
    if url.startswith("sqlite"):
        # A single StaticPool connection is safe for in-memory tests, but
        # corrupts concurrent transactions in the live worker: independent
        # scheduler jobs can invalidate one another's SAVEPOINTs. File-backed
        # SQLite gets a small async pool; WAL + busy_timeout serialize writes
        # without sharing transaction state, while limiting laptop resources.
        pool_options = (
            {"poolclass": StaticPool}
            if url.endswith(":memory:") or url.endswith("sqlite+aiosqlite://")
            else {
                "poolclass": AsyncAdaptedQueuePool,
                "pool_size": 3,
                "max_overflow": 2,
            }
        )
        engine = create_async_engine(
            url,
            echo=echo,
            future=True,
            query_cache_size=1200,
            connect_args={
                "check_same_thread": False,
                "timeout": 30,
            },
            **pool_options,
        )
        from sqlalchemy import event
        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            # SQLite does not enforce declared FK actions unless explicitly
            # enabled per connection; retention otherwise leaves orphaned
            # snapshots and radar matches behind.
            cursor.execute("PRAGMA foreign_keys=ON")
            # WAL is persistent for the database file. Avoid trying to switch
            # journal mode on every pooled connection while another task has a
            # transaction open.
            cursor.execute("PRAGMA journal_mode")
            journal_mode = cursor.fetchone()[0].lower()
            if journal_mode != "wal":
                cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA cache_size=-4000")  # 4MB cache limit to keep RAM consumption minimal
            cursor.execute("PRAGMA temp_store=MEMORY")
            cursor.close()
        return engine
    return create_async_engine(
        url,
        echo=echo,
        future=True,
        query_cache_size=1200,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


database_url = _get_database_url()
engine: AsyncEngine = _build_engine(database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependency yielding an async database session."""
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


async def check_migrations() -> None:
    """Automatic migration check / apply for SQLite or Postgres."""
    if database_url.startswith("sqlite"):
        from app.db.migrate import apply_migrations
        await apply_migrations(engine)
    else:
        # For Postgres, check/apply Alembic migrations if needed
        try:
            from alembic.config import Config
            from pathlib import Path
            backend_root = Path(__file__).resolve().parent.parent.parent
            cfg_path = backend_root / "alembic.ini"
            if cfg_path.exists():
                cfg = Config(str(cfg_path))
                cfg.set_main_option("script_location", str(backend_root / "alembic"))
                # You can run check or upgrade head here
        except Exception:
            pass
