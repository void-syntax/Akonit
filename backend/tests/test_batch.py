"""Tests for BatchEventIngester pipeline optimization."""

from __future__ import annotations

import pytest
from app.core.database import SessionLocal
from app.pipeline.batch import BatchEventIngester


@pytest.mark.asyncio
async def test_batch_ingester_buffering():
    ingester = BatchEventIngester(batch_size=2)
    async with SessionLocal() as session:
        c1 = await ingester.add(session, {"id": "1", "title": "Test 1"})
        assert c1 == 0  # Not flushed yet
        
        c2 = await ingester.add(session, {"id": "2", "title": "Test 2"})
        assert c2 == 2  # Flushed batch
        
        # Flush remaining
        c3 = await ingester.flush(session)
        assert c3 == 0
