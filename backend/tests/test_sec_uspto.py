"""Tests for SEC EDGAR and USPTO Patents collectors (`backend/tests/test_sec_uspto.py`)."""

from __future__ import annotations

import pytest
from app.pipeline.collectors import get_adapter, registry_snapshot
from app.pipeline.collectors.adapters.sec_edgar import SecEdgarAdapter, SecEdgarRssStrategy
from app.pipeline.collectors.adapters.uspto_patents import UsptoPatentsAdapter, UsptoPatentApiStrategy
from app.pipeline.collectors.base import FetchContext


def test_sec_edgar_registration():
    adapter = get_adapter("sec_edgar")
    assert adapter is not None
    assert isinstance(adapter, SecEdgarAdapter)
    assert adapter.source_id == "sec_edgar"
    assert "form_d" in adapter.capabilities
    assert "form_4" in adapter.capabilities
    assert "alpha_score" in adapter.capabilities

    snapshot = registry_snapshot()
    source_ids = [s["id"] for s in snapshot]
    assert "sec_edgar" in source_ids


def test_uspto_patents_registration():
    adapter = get_adapter("uspto_patents")
    assert adapter is not None
    assert isinstance(adapter, UsptoPatentsAdapter)
    assert adapter.source_id == "uspto_patents"
    assert "patents" in adapter.capabilities
    assert "breakthrough_score" in adapter.capabilities

    snapshot = registry_snapshot()
    source_ids = [s["id"] for s in snapshot]
    assert "uspto_patents" in source_ids


@pytest.mark.asyncio
async def test_sec_edgar_strategy_parsing():
    strategy = SecEdgarRssStrategy()
    company, amount, exec_name, sentiment = strategy._parse_sec_details("D", "Acme AI Corp - Form D Offering", "Offering of $15,000,000 in equity")
    assert company == "Acme AI Corp"
    assert amount == 15_000_000.0
    assert sentiment == "bullish"

    score = strategy._calculate_alpha_score("D", 15_000_000.0, "bullish")
    assert score >= 80.0


@pytest.mark.asyncio
async def test_uspto_fallback_patents():
    strategy = UsptoPatentApiStrategy()
    ctx = FetchContext(limit=2)
    events = strategy._get_fallback_patent_events(ctx)
    assert len(events) == 2
    assert events[0].source_id == "uspto_patents"
    assert events[0].metadata["breakthrough_score"] > 0
    assert "Patent" in events[0].title
