"""Signal Radar API."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, notifications, radars, signals, stream, system, taxonomy
from app.core.config import settings
from app.core.logging import get_logger
from app.db.redis_bus import close_redis, get_redis
from app.db.session import init_models

logger = get_logger(__name__)

DESCRIPTION = """
Condition-driven signal radar.

You define the conditions, the system monitors the internet 24/7,
early signals appear, and you get notified.
"""


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from app.db import session as db_session

    # Resolve the real database before anything touches it.
    db_session.engine = await db_session.create_engine()
    db_session.SessionLocal.configure(bind=db_session.engine)

    # Check the engine that is actually in use, not the configured URL: the
    # fallback may have swapped a Postgres URL for a local SQLite file.
    active_url = db_session.engine.url.render_as_string(hide_password=False)
    on_sqlite = str(db_session.engine.url).startswith("sqlite")

    if on_sqlite:
        await db_session.init_models()

        from app.db.migrate import apply_migrations

        added = await apply_migrations(db_session.engine)
        if added:
            logger.info("schema migrated: %s", ", ".join(added))
    else:
        import asyncio
        from pathlib import Path

        from alembic import command
        from alembic.config import Config as AlembicConfig
        from sqlalchemy import text

        # The Supabase schema predates Alembic, so the tables can already exist
        # while alembic_version is empty; a bare upgrade would then fail on
        # CREATE TABLE. Stamp the baseline first when that is the case.
        async with db_session.engine.connect() as conn:
            versioned = await conn.execute(
                text("SELECT to_regclass('public.alembic_version')")
            )
            signals = await conn.execute(text("SELECT to_regclass('public.signals')"))
            needs_stamp = versioned.scalar() is None and signals.scalar() is not None

        def _migrate() -> None:
            cfg = AlembicConfig(
                str(Path(__file__).resolve().parent.parent / "alembic.ini")
            )
            cfg.set_main_option("sqlalchemy.url", active_url)
            if needs_stamp:
                command.stamp(cfg, "head")
            command.upgrade(cfg, "head")

        # alembic/env.py calls asyncio.run() itself, so it needs a thread that
        # has no running event loop.
        await asyncio.to_thread(_migrate)
        logger.info("schema ready (alembic head)")

    from app.db.session import SessionLocal
    from app.seed.runner import seed_countries, seed_sources, seed_tags

    async with SessionLocal() as session:
        await seed_countries(session)
        await seed_tags(session)
        await seed_sources(session)

    await get_redis()
    logger.info("Signal Radar API ready (%s sources)", len(_sources()))
    yield
    await close_redis()
    await db_session.engine.dispose()


def _sources() -> list:
    from app.pipeline.collectors import all_adapters

    return all_adapters()


app = FastAPI(
    title="Signal Radar",
    description=DESCRIPTION,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API = "/api/v1"
app.include_router(auth.router, prefix=API)
app.include_router(taxonomy.router, prefix=API)
app.include_router(taxonomy.custom_router, prefix=API)
app.include_router(radars.router, prefix=API)
app.include_router(signals.router, prefix=API)
app.include_router(signals.saved_router, prefix=API)
app.include_router(notifications.router, prefix=API)
app.include_router(system.router, prefix=API)
app.include_router(stream.router, prefix=API)


@app.get("/")
async def root():
    return {
        "name": "Signal Radar",
        "docs": "/docs",
        "principle": "You decide what to watch. Signal Radar watches it 24/7.",
    }