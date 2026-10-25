"""Tests for database index optimization module."""

from __future__ import annotations

import pytest
from app.core.database import SessionLocal
from app.core.indexes import ensure_optimal_indexes


@pytest.mark.asyncio
async def test_ensure_optimal_indexes():
    async with SessionLocal() as session:
        await ensure_optimal_indexes(session)
        # Should execute successfully without throwing errors
        assert True
