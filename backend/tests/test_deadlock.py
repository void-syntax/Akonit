"""Tests for transaction timeout guard."""

from __future__ import annotations

import asyncio
import pytest
from app.core.deadlock import with_transaction_timeout


@pytest.mark.asyncio
async def test_transaction_timeout_success():
    async def fast_task() -> str:
        return "done"

    res = await with_transaction_timeout(fast_task(), timeout_seconds=1.0)
    assert res == "done"


@pytest.mark.asyncio
async def test_transaction_timeout_expires():
    async def slow_task() -> str:
        await asyncio.sleep(0.2)
        return "too_late"

    with pytest.raises(asyncio.TimeoutError):
        await with_transaction_timeout(slow_task(), timeout_seconds=0.05)
