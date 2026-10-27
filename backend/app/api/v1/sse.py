"""Server-Sent Events (SSE) Real-Time Telemetry & Signal Stream Router (`backend/app/api/v1/sse.py`).

Provides real-time asynchronous streaming of signal updates and telemetry pulses to clients.
"""

from __future__ import annotations

import asyncio
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.core.logging import get_logger

logger = get_logger("app.api.v1.sse")

router = APIRouter(prefix="/sse", tags=["sse"])


@router.get("/stream")
async def sse_stream() -> StreamingResponse:
    """Stream real-time intelligence telemetry and signal updates via SSE."""
    async def event_generator():
        try:
            for i in range(5):
                payload = {
                    "event": "pulse",
                    "sequence": i + 1,
                    "status": "nominal",
                    "timestamp": asyncio.get_event_loop().time()
                }
                yield f"data: {json.dumps(payload)}\n\n"
                await asyncio.sleep(0.5)
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
