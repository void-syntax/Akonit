"""Tests for PipelineConcurrencyLimiter module."""

from __future__ import annotations

import asyncio
import pytest
from app.pipeline.limiter import PipelineConcurrencyLimiter


@pytest.mark.asyncio
async def test_pipeline_concurrency_limiter():
    limiter = PipelineConcurrencyLimiter(max_concurrent=2)
    counter = 0

    async def sample_task(val: int) -> int:
        nonlocal counter
        counter += 1
        await asyncio.sleep(0.01)
        return val * 2

    results = await asyncio.gather(
        limiter.run(sample_task, 1),
        limiter.run(sample_task, 2),
        limiter.run(sample_task, 3),
    )

    assert results == [2, 4, 6]
    assert counter == 3
