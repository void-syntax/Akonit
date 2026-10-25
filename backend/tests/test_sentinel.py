"""Tests for CollectorSentinel auto-recovery service."""

from __future__ import annotations

import pytest
from app.pipeline.sentinel import CollectorSentinel


@pytest.mark.asyncio
async def test_collector_sentinel_sweep():
    sentinel = CollectorSentinel()
    tripped = await sentinel.sweep()
    assert isinstance(tripped, int)
