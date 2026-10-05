"""Shared bootstrap for the CLI tools.

The API resolves the database in its lifespan; a standalone script has to do the
same, otherwise it would connect to DATABASE_URL directly and ignore an explicit
fallback.

Schema ownership is Alembic's alone. The collection tools run in GitHub Actions
against Postgres, where `alembic upgrade head` is the one thing allowed to change
the schema, so `prepare()` brings the database to head instead of poking at it
with ad-hoc DDL.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _albic_config():  # noqa: ANN202
    from alembic.config import Config

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return config


async def _needs_baseline() -> bool:
    """True when the tables exist but Alembic has never recorded a revision.

    The Supabase schema was applied by hand before Alembic existed, so a
    database can already hold every table while `alembic_version` is empty. An
    unconditional `upgrade head` would then fail on `CREATE TABLE` for a table
    that is already there.
    """
    from sqlalchemy import text

    from app.db.session import engine

    async with engine.connect() as conn:
        versioned = await conn.execute(
            text("SELECT to_regclass('public.alembic_version')")
        )
        if versioned.scalar() is not None:
            return False
        signals = await conn.execute(text("SELECT to_regclass('public.signals')"))
        return signals.scalar() is not None


def _apply_alembic(stamp: bool) -> None:
    """Run Alembic from a thread, since env.py calls asyncio.run() itself."""
    from alembic import command

    config = _alembic_config()
    if stamp:
        command.stamp(config, "head")
    # After stamping, this applies only the genuine delta; when the schema is
    # already current it is a no-op.
    command.upgrade(config, "head")


async def prepare() -> None:
    """Point the shared engine and session factory at the resolved database."""
    from app.db import session as db_session

    db_session.engine = await db_session.create_engine()
    db_session.SessionLocal.configure(bind=db_session.engine)

    stamp = await _needs_baseline()
    if stamp:
        print("schema already present; stamping alembic baseline at head")

    await asyncio.to_thread(_apply_alembic, stamp)


def run(coro):  # noqa: ANN001, ANN201
    """Run an async entry point after the database is ready."""

    async def wrapper():
        await prepare()
        return await coro

    return asyncio.run(wrapper())


async def empty() -> None:
    """No-op placeholder so run() can accept a bare coroutine factory."""
    return None