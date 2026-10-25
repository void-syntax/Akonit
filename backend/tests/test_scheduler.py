"""Tests for AsyncBackgroundScheduler module."""

from __future__ import annotations

import asyncio
import pytest
from app.core.scheduler import AsyncBackgroundScheduler


@pytest.mark.asyncio
async def test_background_scheduler():
    scheduler = AsyncBackgroundScheduler()
    executed = 0

    async def dummy_task() -> None:
        nonlocal executed
        executed += 1

    scheduler.schedule_interval(0.05, dummy_task)
    await asyncio.sleep(0.08)
    scheduler.shutdown()

    assert executed >= 1
