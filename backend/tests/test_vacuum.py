"""Tests for database vacuum optimization module."""

from __future__ import annotations

import pytest
from app.core.database import SessionLocal
from app.core.vacuum import optimize_storage


@pytest.mark.asyncio
async def test_optimize_storage():
    async with SessionLocal() as session:
        res = await optimize_storage(session)
        assert "status" in res
