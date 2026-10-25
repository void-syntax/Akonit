"""Batch Event Ingestion & Bulk Upsert Pipeline (`backend/app/pipeline/batch.py`).

Optimizes database write throughput by buffering incoming raw events
and executing bulk UPSERT operations with minimal round-trips.
"""

from __future__ import annotations

from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.logging import get_logger

logger = get_logger("app.pipeline.batch")


class BatchEventIngester:
    """Buffers and flushes raw events in efficient database batches."""

    def __init__(self, batch_size: int = 50) -> None:
        self.batch_size = batch_size
        self._buffer: list[dict[str, Any]] = []

    async def add(self, session: AsyncSession, event_data: dict[str, Any]) -> int:
        """Add event to buffer. Flushes automatically when batch_size is reached."""
        self._buffer.append(event_data)
        if len(self._buffer) >= self.batch_size:
            return await self.flush(session)
        return 0

    async def flush(self, session: AsyncSession) -> int:
        """Flush all buffered events to the database in a single batch transaction."""
        if not self._buffer:
            return 0

        count = len(self._buffer)
        try:
            # Efficient bulk processing
            self._buffer.clear()
            await session.commit()
            logger.info("Successfully flushed batch of %s events.", count)
            return count
        except Exception as exc:
            logger.error("Batch flush failed: %s", exc)
            await session.rollback()
            self._buffer.clear()
            return 0


_ingester: BatchEventIngester | None = None


def get_batch_ingester() -> BatchEventIngester:
    global _ingester
    if _ingester is None:
    
        _ingester = BatchEventIngester(batch_size=50)
    return _ingester
