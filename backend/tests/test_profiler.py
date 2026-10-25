"""Tests for query performance profiler decorator."""

from __future__ import annotations

import asyncio
import pytest
from app.core.profiler import profile_query


@pytest.mark.asyncio
async def test_profile_query():
    @profile_query(threshold_seconds=0.01)
    async def fast_db_call() -> str:
        await asyncio.sleep(0.002)
        return "ok"

    res = await fast_db_call()
    assert res == "ok"
