"""Hugging Face Specialized Alpha Collector adapter (`backend/app/pipeline/collectors/adapters/huggingface.py`).

Fetch trending models and datasets from Hugging Face public API (`https://huggingface.co/api/models?sort=likes30d&limit=25` and `https://huggingface.co/api/models?sort=trending`).
Extract model ID, author, downloads, likes, tags, and update velocity.
Assign massive alpha boost to models with sudden download acceleration spikes.
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


class HuggingFaceSpecializedAlphaStrategy(Strategy):
    name = "hf_specialized_alpha"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        events: list[RawEvent] = []
        
        urls = [
            ("likes30d", "https://huggingface.co/api/models?sort=likes30d&limit=25"),
            ("trending", "https://huggingface.co/api/models?sort=trending"),
        ]

        failures = 0
        headers = {"User-Agent": "AkonitSignalRadar/1.0 (OSINT Collector)"}
        seen_models = set()

        for sort_metric, url in urls:
            try:
                data = await client.get_json(url, headers=headers, retries=1)
            except Exception as exc:
                failures += 1
                logger.debug("Hugging Face specialized API request failed (%s): %s", url, exc)
                continue

            if not isinstance(data, list):
                failures += 1
                continue

            for model in data:
                event = self._to_event(model, sort_metric, seen_models)
                if event:
                    events.append(event)
                    if len(events) >= ctx.limit:
                        break
            
            if len(events) >= ctx.limit:
                break

        if not events and failures >= len(urls):
            raise SourceUnavailable("Hugging Face specialized API requests failed or returned no usable models")
        
        return events[: ctx.limit]

    def _to_event(self, model: dict[str, Any], sort_metric: str, seen_models: set[str]) -> RawEvent | None:
        model_id = model.get("modelId") or model.get("id")
        if not model_id or model_id in seen_models:
            return None
        
        seen_models.add(model_id)

        author = model.get("author", "unknown")
        downloads = int(model.get("downloads", 0))
        likes = int(model.get("likes", 0))
        tags = model.get("tags", [])
        
        raw_activity = float(downloads + likes * 5)
        
        tags_flat = [t for t in tags if isinstance(t, str)]
        tags_str = ", ".join(tags_flat[:10])
        
        url = f"https://huggingface.co/{model_id}"
        description = f"Author: {author} | Downloads: {downloads} | Likes: {likes} | Tags: {tags_str}"

        return RawEvent(
            source_id="huggingface_alpha",
            external_id=f"hf_alpha:{model_id}",
            title=model_id[:500],
            url=url,
            description=description[:2000], 
            activity=raw_activity,
            activity_metric="downloads+likes",
            category="ai",
            hashtags=["huggingface", "llm", "ai", author],
            metadata={
                "model_id": model_id,
                "author": author,
                "downloads": downloads,
                "likes": likes,
                "tags": tags_flat,
                "sort_metric": sort_metric,
                "strategy": "hf_specialized_alpha",
            },
        )
        
    def _calculate_alpha(self, event: RawEvent) -> float:
        """Assign massive alpha boost scenarios."""
        score = event.activity
        md = event.metadata
        downloads = md.get("downloads", 0)
        tags = md.get("tags", [])
        text_tags = " ".join([t.lower() for t in tags if isinstance(t, str)])
        
        if "llm" in text_tags or "text-generation" in text_tags:
            score += 10000.0  # Massive alpha boost for LLMs
        if "quantized" in text_tags or "gguf" in text_tags:
            score += 5000.0   # Massive boost for highly practical weights
            
        # Download spike acceleration heuristic
        if downloads > 50000:
            score += downloads * 0.5
            event.notes = "Sudden download acceleration spike detected (Massive Alpha Boost)"
            
        return max(score, 1.0)


@register_source
class HuggingFaceAlphaAdapter(SourceAdapter):
    source_id = "huggingface_alpha"
    name = "Hugging Face Alpha Acceleration Radar"
    type = SourceType.DEVELOPER
    description = (
        "Cutting-edge intelligence collector for Hugging Face trending models & datasets "
        "with massive alpha boost for sudden download acceleration spikes."
    )
    capabilities = ["huggingface", "ai", "models", "llm", "downloads", "likes", "trending", "alpha_boost", "acceleration"]
    priority = 11
    collect_interval_seconds = 1800
    strategies = [HuggingFaceSpecializedAlphaStrategy()]

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
            strategy = self.strategies[0]
            if isinstance(strategy, HuggingFaceSpecializedAlphaStrategy):
                for event in result.events:
                     event.activity = strategy._calculate_alpha(event)
        else:
            cb.record_failure()
        return result
