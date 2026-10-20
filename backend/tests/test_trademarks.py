"""Tests for Trademarks Intelligence Collector adapter (`backend/tests/test_trademarks.py`)."""

from __future__ import annotations

import pytest
from app.pipeline.collectors import get_adapter, registry_snapshot
from app.pipeline.collectors.adapters.trademarks import TrademarksAdapter, TrademarksApiStrategy
from app.pipeline.collectors.base import FetchContext


def test_trademarks_registration():
    adapter = get_adapter("trademarks")
    assert adapter is not None
    assert isinstance(adapter, TrademarksAdapter)
    assert adapter.source_id == "trademarks"
    assert "trademarks" in adapter.capabilities
    assert "stealth_launch" in adapter.capabilities
    assert "brand_value_score" in adapter.capabilities

    snapshot = registry_snapshot()
    source_ids = [s["id"] for s in snapshot]
    assert "trademarks" in source_ids


@pytest.mark.asyncio
async def test_trademarks_scoring():
    strategy = TrademarksApiStrategy()
    stealth_prob, brand_score = strategy._calculate_stealth_and_brand_score(
        "NEURACLAW", "Anthropic Stealth Sub-Four LLC", "Autonomous agent AI software"
    )
    assert 0.0 <= stealth_prob <= 1.0
    assert stealth_prob >= 0.8
    assert 10.0 <= brand_score <= 100.0
    assert brand_score >= 85.0


@pytest.mark.asyncio
async def test_trademarks_fallback_events():
    strategy = TrademarksApiStrategy()
    ctx = FetchContext(limit=3)
    events = strategy._get_fallback_trademark_events(ctx)
    assert len(events) == 3
    assert events[0].source_id == "trademarks"
    assert events[0].metadata["stealth_launch_probability"] > 0.0
    assert events[0].metadata["brand_value_score"] > 0.0
    assert "Trademark" in events[0].title
