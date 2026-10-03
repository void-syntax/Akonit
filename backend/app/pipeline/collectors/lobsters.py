"""Lobsters - new developer tools, side projects and tech releases."""

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


class LobstersRssStrategy(Strategy):
    name = "rss_feed"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        from app.pipeline.collectors.rss_utils import parse_feed

        xml = await client.get_text("https://lobste.rs/rss", retries=1)
        events: list[RawEvent] = []
        for rank, item in enumerate(parse_feed(xml), start=1):
            if not item["title"] or not item["link"]:
                continue
            events.append(
                RawEvent(
                    source_id="lobsters",
                    external_id=f"lob:{item['link'].rsplit('/', 1)[-1][:40]}",
                    title=item["title"][:500],
                    url=item["link"],
                    description=(item["description"] or "")[:400],
                    activity=0.0,
                    activity_metric="comments",
                    category="tech",
                    hashtags=item["tags"],
                    published_at=item["published"],
                    metadata={"rank": rank, "strategy": "rss_feed"},
                )
            )
        if not events:
            raise SourceUnavailable("lobsters feed empty")
        return events[: ctx.limit]


@register_source
class LobstersAdapter(SourceAdapter):
    source_id = "lobsters"
    name = "Lobsters"
    type = SourceType.COMMUNITY
    description = "New developer tools, side projects and tech releases."
    capabilities = ["dev_tools", "side_projects", "tech", "new_software"]
    priority = 29
    collect_interval_seconds = 3600
    strategies = [LobstersRssStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)