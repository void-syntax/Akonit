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
    if settings.is_sqlite:
        await init_models()
    from app.seed.runner import seed_countries, seed_sources, seed_tags

    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        await seed_countries(session)
        await seed_tags(session)
        await seed_sources(session)
    await get_redis()
    logger.info("Signal Radar API ready (%s sources)", len(_sources()))
    yield
    await close_redis()


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