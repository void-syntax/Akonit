from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from app.pipeline.collectors import get_adapter, registry_snapshot
from app.pipeline.collectors.adapters.huggingface import HuggingFaceAlphaAdapter, HuggingFaceSpecializedAlphaStrategy
from app.pipeline.collectors.adapters.polymarket import PolymarketAdapter, PolymarketGammaStrategy
from app.pipeline.collectors.base import FetchContext
from app.pipeline.collectors.ai_tech import GitHubSearchStrategy


@pytest.mark.asyncio
async def test_github_search_uses_bounded_discovery_queries_and_deduplicates():
    from app.core.cache import clear_memory_cache
    await clear_memory_cache()
    strategy = GitHubSearchStrategy()
    mock_client = AsyncMock()

    def response_for(url, **kwargs):
        from urllib.parse import unquote

        query = unquote(url.split("?q=", 1)[1].split("&", 1)[0])
        if "robotics" in query:
            names = ["fast/project"]
        elif "sensors" in query:
            names = ["popular/project"]
        elif "stars:>10" in query:
            names = ["fast/project", "popular/project"]
        else:
            names = ["fast/project"]
        return {
            "items": [
                {
                    "full_name": name,
                    "stargazers_count": 100 if name.startswith("fast") else 300,
                    "forks_count": 2,
                    "created_at": "2026-10-24T00:00:00Z",
                    "description": "A useful open source project with details",
                    "html_url": f"https://github.com/{name}",
                    "owner": {},
                    "topics": [],
                }
                for name in names
            ]
        }

    mock_client.get_json.side_effect = response_for
    events = await strategy.fetch(
        mock_client, FetchContext(keywords=["robotics", "sensors"], limit=10)
    )

    assert mock_client.get_json.await_count == 2
    assert len(events) == 2
    assert {events[0].title, events[1].title} == {"fast/project", "popular/project"}
    first_query = mock_client.get_json.await_args_list[0].args[0]
    assert "robotics" in first_query


def test_huggingface_alpha_registration():
    adapter = get_adapter("huggingface_alpha")
    assert adapter is not None
    assert isinstance(adapter, HuggingFaceAlphaAdapter)
    assert adapter.source_id == "huggingface_alpha"
    assert "huggingface" in adapter.capabilities
    assert "llm" in adapter.capabilities
    assert "alpha_boost" in adapter.capabilities

    snapshot = registry_snapshot()
    source_ids = [s["id"] for s in snapshot]
    assert "huggingface_alpha" in source_ids


def test_polymarket_registration():
    adapter = get_adapter("polymarket")
    assert adapter is not None
    assert isinstance(adapter, PolymarketAdapter)
    assert adapter.source_id == "polymarket"
    assert "polymarket" in adapter.capabilities
    assert "prediction_markets" in adapter.capabilities
    assert "alpha_boost" in adapter.capabilities

    snapshot = registry_snapshot()
    source_ids = [s["id"] for s in snapshot]
    assert "polymarket" in source_ids


@pytest.mark.asyncio
async def test_huggingface_alpha_strategy_fetch():
    strategy = HuggingFaceSpecializedAlphaStrategy()
    mock_client = AsyncMock()
    mock_client.get_json.return_value = [
        {
            "modelId": "meta-llama/Llama-3-70B-Instruct",
            "author": "meta-llama",
            "downloads": 150000,
            "likes": 2500,
            "tags": ["pytorch", "safetensors", "llama", "text-generation", "llm"],
        }
    ]

    ctx = FetchContext(limit=10)
    events = await strategy.fetch(mock_client, ctx)
    assert len(events) == 1
    event = events[0]
    assert event.source_id == "huggingface_alpha"
    assert event.external_id == "hf_alpha:meta-llama/Llama-3-70B-Instruct"
    assert event.title == "meta-llama/Llama-3-70B-Instruct"
    
    adapter = HuggingFaceAlphaAdapter()
    alpha_score = adapter.strategies[0]._calculate_alpha(event)
    assert alpha_score > 100000


@pytest.mark.asyncio
async def test_polymarket_strategy_fetch():
    strategy = PolymarketGammaStrategy()
    mock_client = AsyncMock()
    mock_client.get_json.return_value = [
        {
            "id": "12345",
            "slug": "will-ai-achieve-agi-by-2027",
            "title": "Will AI achieve AGI by 2027?",
            "description": "Prediction market on AGI timeline.",
            "volume": 9000000.0,
            "volume24hr": 600000.0,
            "liquidity": 50000.0,
            "markets": [
                {
                    "question": "Will AI achieve AGI by 2027?",
                    "outcomePrices": ["0.45", "0.55"],
                    "volume": 600000.0,
                }
            ]
        }
    ]

    ctx = FetchContext(limit=10)
    events = await strategy.fetch(mock_client, ctx)
    assert len(events) == 1
    event = events[0]
    assert event.source_id == "polymarket"
    assert event.external_id == "poly:12345"
    assert event.title == "Will AI achieve AGI by 2027?"
    assert event.metadata["high_conviction"] is True
    assert event.metadata["volume"] == 9000000.0
    assert event.metadata["volume_24h"] == 600000.0
    assert "Massive Volume Surge" in event.metadata["notes"]


def test_polymarket_ignores_expired_event():
    strategy = PolymarketGammaStrategy()
    event = strategy._to_event({
        "id": "old-event",
        "title": "An event that already ended",
        "endDate": "2024-01-01T00:00:00Z",
    })
    assert event is None


def test_polymarket_uses_market_creation_time_for_freshness():
    strategy = PolymarketGammaStrategy()
    event = strategy._to_event({
        "id": "recent-event",
        "title": "A recent market",
        "createdAt": "2026-10-23T09:00:00Z",
        "endDate": "2026-12-31T00:00:00Z",
    })
    assert event is not None
    assert event.published_at is not None
    assert event.published_at.isoformat() == "2026-10-23T09:00:00+00:00"
