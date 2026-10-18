"""RSS / News collector adapter for TechCrunch, HackerNews, Bloomberg RSS feeds."""

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
from app.pipeline.collectors.rss_utils import parse_feed


class RssNewsStrategy(Strategy):
    name = "rss_feeds"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        feeds = [
            ("techcrunch", "https://techcrunch.com/feed/", "TechCrunch"),
            ("hackernews_rss", "https://hnrss.org/frontpage", "Hacker News RSS"),
            ("bloomberg", "https://feeds.bloomberg.com/technology/news.rss", "Bloomberg Tech"),
        ]

        events: list[RawEvent] = []
        for feed_id, url, feed_name in feeds:
            try:
                xml = await client.get_text(url, retries=1)
            except Exception:
                continue

            items = parse_feed(xml)
            for rank, item in enumerate(items, start=1):
                title = item.get("title")
                link = item.get("link")
                if not title or not link:
                    continue

                events.append(
                    RawEvent(
                        source_id="rss_news",
                        external_id=f"{feed_id}:{link.rsplit('/', 1)[-1][:40]}",
                        title=title[:500],
                        url=link,
                        description=(item.get("description") or "")[:400],
                        activity=0.0,
                        activity_metric="news_mentions",
                        category="news",
                        hashtags=item.get("tags", []),
                        published_at=item.get("published"),
                        metadata={
                            "feed_id": feed_id,
                            "feed_name": feed_name,
                            "rank": rank,
                            "strategy": "rss_feeds",
                        },
                    )
                )

        if not events:
            raise SourceUnavailable("all RSS news feeds returned no items")
        return events[: ctx.limit]


@register_source
class RssNewsAdapter(SourceAdapter):
    source_id = "rss_news"
    name = "Global RSS News (TechCrunch, HN, Bloomberg)"
    type = SourceType.NEWS
    description = (
        "Latest tech, startup and financial news from TechCrunch, "
        "HackerNews and Bloomberg RSS feeds."
    )
    capabilities = ["news", "techcrunch", "hackernews", "bloomberg", "breaking_news", "startups"]
    priority = 27
    collect_interval_seconds = 1800
    strategies = [RssNewsStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)
