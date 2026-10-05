"""Shared bootstrap for the CLI tools.

The API creates its tables in its lifespan; a standalone script has to do the
same, otherwise it would query a database that does not have them yet.

Schema ownership is Alembic's alone. These tools bring the database to head
rather than poking at it with ad-hoc DDL, so a script can never leave the schema
in a state the API would not understand.
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


async def _already_at_head() -> bool:
    """True when Alembic has recorded the current revision.

    A database can hold every table while `alembic_version` is empty, in which
    case `upgrade head` would fail on `CREATE TABLE` for a table that is already
    there. SQLite never has an `alembic_version` at all, and is handled by the
    caller instead.
    """
    from sqlalchemy import text

    from app.core.config import settings
    from app.db.session import engine

    if settings.is_sqlite:
        return True

    async with engine.connect() as conn:
        exists = await conn.execute(
            text("SELECT to_regclass('public.alembic_version')")
        )
        return exists.scalar() is not None


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
    """Make sure the database exists and is at the current revision."""
    from app.core.config import settings

    if settings.is_sqlite:
        # The Postgres-flavoured migration cannot run against a file SQLite
        # database, and the API creates those tables directly.
        from app.db.session import init_models

        await init_models()
        return

    stamp = not await _already_at_head()
    if stamp:
        print("schema present without an alembic revision; stamping at head")
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