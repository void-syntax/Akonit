"""Tests for performance benchmarker module."""

from __future__ import annotations

import asyncio
import pytest
from app.core.benchmarker import benchmark_async_operation


@pytest.mark.asyncio
async def test_benchmark_async_operation():
    async def sample_op(x: int) -> int:
        await asyncio.sleep(0.01)
        return x * 10

    res = await benchmark_async_operation("test_op", sample_op, 5)
    assert res["success"] is True
    assert res["result"] == 50
    assert res["duration_seconds"] > 0
