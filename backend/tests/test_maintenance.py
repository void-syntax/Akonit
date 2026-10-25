"""Tests for SQLite database maintenance module."""

from __future__ import annotations

import pytest
from app.core.database import SessionLocal
from app.core.maintenance import run_sqlite_maintenance


@pytest.mark.asyncio
async def test_sqlite_maintenance():
    async with SessionLocal() as session:
        stats = await run_sqlite_maintenance(session)
        assert stats["status"] == "success"
        assert "wal_checkpoint_truncate" in stats["operations"]
        assert "page_count" in stats
        assert "freelist_count" in stats
        assert "duration_seconds" in stats
