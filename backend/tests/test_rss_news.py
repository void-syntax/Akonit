from __future__ import annotations

import pytest
from app.pipeline.collectors import get_adapter, registry_snapshot
from app.pipeline.collectors.adapters.rss_news import RssNewsAdapter


def test_rss_news_registration():
    adapter = get_adapter("rss_news")
    assert adapter is not None
    assert isinstance(adapter, RssNewsAdapter)
    assert adapter.source_id == "rss_news"
    assert "techcrunch" in adapter.capabilities
    assert "hackernews" in adapter.capabilities
    assert "bloomberg" in adapter.capabilities

    snapshot = registry_snapshot()
    source_ids = [s["id"] for s in snapshot]
    assert "rss_news" in source_ids
