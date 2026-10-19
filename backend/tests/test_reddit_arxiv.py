from __future__ import annotations

import pytest
from app.pipeline.collectors import get_adapter, registry_snapshot
from app.pipeline.collectors.adapters.reddit import RedditOsintAdapter
from app.pipeline.collectors.adapters.arxiv import ArxivAdapter


def test_reddit_osint_registration():
    adapter = get_adapter("reddit_osint")
    assert adapter is not None
    assert isinstance(adapter, RedditOsintAdapter)
    assert adapter.source_id == "reddit_osint"
    assert "machinelearning" in adapter.capabilities
    assert "programming" in adapter.capabilities
    assert "startups" in adapter.capabilities

    snapshot = registry_snapshot()
    source_ids = [s["id"] for s in snapshot]
    assert "reddit_osint" in source_ids


def test_arxiv_registration():
    adapter = get_adapter("arxiv")
    assert adapter is not None
    assert isinstance(adapter, ArxivAdapter)
    assert adapter.source_id == "arxiv"
    assert "arxiv" in adapter.capabilities
    assert "machine_learning" in adapter.capabilities
    assert "commercial_applicability" in adapter.capabilities

    snapshot = registry_snapshot()
    source_ids = [s["id"] for s in snapshot]
    assert "arxiv" in source_ids
