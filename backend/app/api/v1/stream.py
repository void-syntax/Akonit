"""Live feed stream (SSE) with a polling fallback."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import SessionDep, get_current_user
from app.core.config import settings
from app.db.redis_bus import publish, subscribe, unsubscribe
from app.models import Signal
from app.models.enums import SignalStatus
from sqlalchemy.orm import selectinload

router = APIRouter(tags=["stream"])

CHANNEL = "feed:signals"
POLL_SECONDS = 30


def serialize(signal: Signal) -> dict:
    return {
        "id": signal.id,
        "title": signal.title,
        "status": signal.status.value,
        "strength": signal.strength,
        "growth": signal.growth,
        "country_code": signal.country_code,
        "source_id": signal.source_id,
        "source_url": signal.source_url,
        "first_seen_at": signal.first_seen_at.isoformat(),
    }


@router.get("/stream/feed")
async def stream_feed(request: Request, session: SessionDep):
    """Server-sent events so the UI updates without a refresh."""

    async def event_source() -> AsyncIterator[str]:
        queue = await subscribe(CHANNEL)
        try:
            latest = (
                (
                    await session.execute(
                        select(Signal)
                        .where(Signal.status != SignalStatus.FADING)
                        .order_by(Signal.first_seen_at.desc())
                        .limit(5)
                        .options(selectinload(Signal.snapshots))
                    )
                )
                .scalars()
                .unique()
                .all()
            )
            yield _sse({"type": "hello", "signals": [serialize(s) for s in latest]})
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=POLL_SECONDS)
                except TimeoutError:
                    yield _sse({"type": "ping"})
                    continue
                yield _sse({"type": "signal", "signal": payload})
        finally:
            await unsubscribe(CHANNEL, queue)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


async def broadcast_signal(signal: Signal) -> None:
    """Called by the pipeline after a signal is created or updated."""
    await publish(CHANNEL, serialize(signal))