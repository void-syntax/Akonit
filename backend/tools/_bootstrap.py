"""Shared bootstrap for the CLI tools.

The API resolves the database in its lifespan; a standalone script has to do the
same, otherwise it would connect to DATABASE_URL directly and ignore an explicit
fallback.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def prepare() -> None:
    """Point the shared engine and session factory at the resolved database."""
    from app.db import session as db_session

    db_session.engine = await db_session.create_engine()
    db_session.SessionLocal.configure(bind=db_session.engine)

    from app.db.session import init_models
    from app.db.migrate import apply_migrations

    await init_models()
    await apply_migrations(db_session.engine)


def run(coro):  # noqa: ANN001, ANN201
    """Run an async entry point after the database is ready."""

    async def wrapper():
        await prepare()
        return await coro

    return asyncio.run(wrapper())


async def empty() -> None:
    """No-op placeholder so run() can accept a bare coroutine factory."""
    return None