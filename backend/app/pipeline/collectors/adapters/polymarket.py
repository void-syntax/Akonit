"""Polymarket Prediction Markets Collector adapter (`backend/app/pipeline/collectors/adapters/polymarket.py`).

Fetches active prediction markets from Polymarket Gamma API.
Extracts title, description, volume, liquidity, and outcome probabilities (prices).
Flags prediction markets with high volume surges as high-conviction future events.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.models.enums import SourceType
from app.pipeline.collectors.base import (
    FetchContext,
    FetchResult,
    RawEvent,
    SourceAdapter,
    SourceUnavailable,
    Strategy,
)
from app.pipeline.collectors.registry import register_source, run_strategy_cascade
from app.pipeline.resilience import get_circuit_breaker, get_rate_limiter

logger = get_logger(__name__)


class PolymarketGammaStrategy(Strategy):
    name = "polymarket_gamma"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        events: list[RawEvent] = []
        
        url = "https://gamma-api.polymarket.com/events?limit=25&active=true&closed=false"
        headers = {"User-Agent": "AkonitSignalRadar/1.0 (OSINT Collector)"}

        try:
            data = await client.get_json(url, headers=headers, retries=1)
        except Exception as exc:
            raise SourceUnavailable(f"Polymarket Gamma API request failed: {exc}") from exc

        if not isinstance(data, list):
            if isinstance(data, dict) and "events" in data:
                data = data["events"]
            else:
                raise SourceUnavailable("Polymarket Gamma API returned unexpected format")

        for item in data:
            event = self._to_event(item)
            if event:
                events.append(event)
                if len(events) >= ctx.limit:
                    break

        if not events:
            raise SourceUnavailable("Polymarket Gamma API returned no active prediction markets")

        return events[: ctx.limit]

    def _to_event(self, item: dict[str, Any]) -> RawEvent | None:
        title = item.get("title") or item.get("question")
        event_id = item.get("id") or item.get("slug")
        if not title or not event_id:
            return None

        description = item.get("description", "")
        volume = float(item.get("volume") or item.get("volume24hr") or 0.0)
        liquidity = float(item.get("liquidity") or 0.0)
        
        markets = item.get("markets", [])
        outcomes_info = []
        
        for m in markets:
            m_title = m.get("question") or m.get("groupItemTitle")
            prices_str = m.get("outcomePrices")
            if isinstance(prices_str, str):
                import json
                try:
                    prices = json.loads(prices_str)
                except Exception:
                    prices = []
            elif isinstance(prices_str, list):
                prices = prices_str
            else:
                prices = []
                
            outcomes_info.append({
                "market_title": m_title,
                "prices": prices,
                "volume": m.get("volume", 0),
            })

        activity = volume + (liquidity * 0.5)
        hashtags = ["polymarket", "prediction", "forecast", "betting"]
        
        notes = None
        if volume > 500000:
            notes = "High-conviction future event (Massive Volume Surge)"
            activity *= 2.0

        url = f"https://polymarket.com/event/{item.get('slug', event_id)}"

        return RawEvent(
            source_id="polymarket",
            external_id=f"poly:{event_id}",
            title=title[:500],
            url=url,
            description=description[:2000],
            activity=activity,
            activity_metric="volume+liquidity",
            category="finance",
            hashtags=hashtags,
            metadata={
                "event_id": event_id,
                "slug": item.get("slug"),
                "volume": volume,
                "liquidity": liquidity,
                "outcomes": outcomes_info,
                "high_conviction": volume > 100000,
                "notes": notes,
                "strategy": "polymarket_gamma",
            },
        )


@register_source
class PolymarketAdapter(SourceAdapter):
    source_id = "polymarket"
    name = "Polymarket Prediction Markets"
    type = SourceType.TREND
    description = (
        "Fetches active prediction markets from Polymarket Gamma API. "
        "Extracts volumes, outcome probabilities, and flags high-conviction future events."
    )
    capabilities = ["polymarket", "prediction_markets", "forecasting", "volume", "liquidity", "finance", "alpha_boost"]
    priority = 13
    collect_interval_seconds = 1800
    strategies = [PolymarketGammaStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        cb = get_circuit_breaker(self.source_id)
        rl = get_rate_limiter(self.source_id)

        if cb.is_open():
            return FetchResult(source_id=self.source_id, events=[], strategy="none", ok=True, notes="circuit open")

        if not await rl.async_acquire():
            return FetchResult(source_id=self.source_id, events=[], strategy="none", ok=True, notes="rate limit exceeded")

        result = await run_strategy_cascade(self, ctx, client)
        if result.ok and result.events:
            cb.record_success()
        else:
            cb.record_failure()
        return result
