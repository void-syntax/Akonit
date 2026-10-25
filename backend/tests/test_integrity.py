"""Tests for database integrity and WAL checkpoint monitor."""

from __future__ import annotations

import pytest
from app.core.database import SessionLocal
from app.core.integrity import verify_database_integrity


@pytest.mark.asyncio
async def test_verify_database_integrity():
    async with SessionLocal() as session:
        res = await verify_database_integrity(session)
        assert "integrity" in res
        assert "status_code" in res
