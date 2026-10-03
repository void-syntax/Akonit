"""Product Hunt - newly launched products. Public RSS feed, no API key."""

from __future__ import annotations

from typing import Any

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


class ProductHuntRssStrategy(Strategy):
    name = "rss_feed"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        from app.pipeline.collectors.rss_utils import parse_feed

        xml = await client.get_text("https://www.producthunt.com/feed", retries=1)
        events: list[RawEvent] = []
        for rank, item in enumerate(parse_feed(xml), start=1):
            if not item["title"] or not item["link"]:
                continue
            events.append(
                RawEvent(
                    source_id="producthunt",
                    external_id=f"ph:{item['link'].rsplit('/', 1)[-1][:40]}",
                    title=item["title"][:500],
                    url=item["link"],
                    description=(item["description"] or "")[:400],
                    activity=0.0,
                    activity_metric="votes",
                    category="product",
                    hashtags=item["tags"],
                    published_at=item["published"],
                    metadata={"rank": rank, "strategy": "rss_feed"},
                )
            )
        if not events:
            raise SourceUnavailable("producthunt feed empty")
        return events[: ctx.limit]


@register_source
class ProductHuntAdapter(SourceAdapter):
    source_id = "producthunt"
    name = "Product Hunt"
    type = SourceType.PRODUCT
    description = "Newly launched products, SaaS and apps via public RSS feed."
    capabilities = ["new_product", "saas", "apps", "services", "ai_products"]
    priority = 25
    collect_interval_seconds = 3600
    strategies = [ProductHuntRssStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)