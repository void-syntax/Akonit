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
from app.core.metrics import active_websocket_connections
from app.db.redis_bus import publish, subscribe, unsubscribe
from app.models import Signal
from app.models.enums import SignalStatus

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

    # Fetch the initial batch while we still hold the DB session, then
    # release it before entering the long-lived streaming loop so we do
    # not pin a connection for the lifetime of the SSE connection.
    latest = (
        (
            await session.execute(
                select(Signal)
                .where(Signal.status != SignalStatus.FADING)
                .order_by(Signal.first_seen_at.desc())
                .limit(5)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    initial_payload = [serialize(s) for s in latest]
    # Release DB resources now — the streaming loop needs no DB access.
    await session.close()

    async def event_source() -> AsyncIterator[str]:
        active_websocket_connections.inc()
        queue = await subscribe(CHANNEL)
        try:
            yield _sse({"type": "hello", "signals": initial_payload})
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
            active_websocket_connections.dec()

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