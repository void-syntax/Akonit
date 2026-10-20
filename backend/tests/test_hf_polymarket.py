from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from app.pipeline.collectors import get_adapter, registry_snapshot
from app.pipeline.collectors.adapters.huggingface import HuggingFaceAlphaAdapter, HuggingFaceSpecializedAlphaStrategy
from app.pipeline.collectors.adapters.polymarket import PolymarketAdapter, PolymarketGammaStrategy
from app.pipeline.collectors.base import FetchContext


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
            "volume": 600000.0,
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
    assert "Massive Volume Surge" in event.metadata["notes"]
