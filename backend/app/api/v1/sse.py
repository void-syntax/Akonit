"""Server-Sent Events (SSE) Real-Time Telemetry & Signal Stream Router (`backend/app/api/v1/sse.py`).

Provides real-time asynchronous streaming of signal updates and telemetry pulses to clients.
"""

from __future__ import annotations

import asyncio
import json
import time
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.core.logging import get_logger

logger = get_logger("app.api.v1.sse")

router = APIRouter(prefix="/sse", tags=["sse"])


@router.get("/stream")
async def sse_stream() -> StreamingResponse:
    """Stream real-time intelligence telemetry and signal updates via SSE."""
    async def event_generator():
        sequence = 0
        try:
            while True:
                sequence += 1
                payload = {
                    "event": "pulse",
                    "sequence": sequence,
                    "status": "nominal",
                    "timestamp": time.time(),
                }
                yield f"data: {json.dumps(payload)}\n\n"
                await asyncio.sleep(15)
        except asyncio.CancelledError:
            logger.info("SSE client disconnected")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
