"""Signal Radar API."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, notifications, radars, signals, stream, system, taxonomy, telemetry
from app.core.cache import close_cache
from app.core.config import settings
from app.core.logging import get_logger
from app.db.redis_bus import close_redis, get_redis

logger = get_logger(__name__)

DESCRIPTION = """
Condition-driven signal radar.

You define the conditions, the system monitors the internet 24/7,
early signals appear, and you get notified.
"""


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from app.db import session as db_session

    on_sqlite = settings.is_sqlite

    if on_sqlite:
        # SQLite has no server to migrate against, so the tables come straight
        # from the models and any leftover file is brought up to date after.
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

        # A database can already hold every table while alembic_version is
        # empty, in which case a bare `upgrade head` would fail on CREATE TABLE.
        # Stamp the baseline first when that is the case.
        async with db_session.engine.connect() as conn:
            versioned = await conn.execute(
                text("SELECT to_regclass('public.alembic_version')")
            )
            existing = await conn.execute(text("SELECT to_regclass('public.signals')"))
            needs_stamp = versioned.scalar() is None and existing.scalar() is not None

        def _migrate() -> None:
            cfg = AlembicConfig(
                str(Path(__file__).resolve().parent.parent / "alembic.ini")
            )
            cfg.set_main_option("sqlalchemy.url", settings.database_url)
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

    # Start optional integrations only when enabled. In particular, avoid
    # loading an AI model on a low-memory local machine by default.
    import asyncio
    from app.bot.telegram_bot import start_bot

    asyncio.create_task(start_bot())
    yield
    await close_redis()
    await close_cache()
    await db_session.engine.dispose()


def _sources() -> list:
    from app.pipeline.collectors import all_adapters

    return all_adapters()


app = FastAPI(
    title="Signal Radar",
    description=DESCRIPTION,
    version="0.1.0",
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
)

from app.core.compression import setup_compression
setup_compression(app, minimum_size=500)

from app.core.tracing import setup_tracing
from app.db.session import engine as db_engine

setup_tracing(app=app, engine=db_engine)

from prometheus_fastapi_instrumentator import Instrumentator

Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

@app.get("/health")
async def root_health():
    return {"status": "ok", "service": "Signal Radar API"}

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
app.include_router(telemetry.router, prefix=API)


@app.get("/")
async def root():
    return {
        "name": "Signal Radar",
        "docs": "/docs",
        "principle": "You decide what to watch. Signal Radar watches it 24/7.",
    }
