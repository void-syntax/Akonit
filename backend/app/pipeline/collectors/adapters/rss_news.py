"""Low-cost RSS news collector for tech and international headlines."""

from __future__ import annotations

import logging
import asyncio
from hashlib import sha256
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
from app.pipeline.resilience import get_circuit_breaker, get_rate_limiter

logger = logging.getLogger(__name__)


class RssNewsStrategy(Strategy):
    name = "rss_feeds"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        feeds = [
            ("techcrunch", "https://techcrunch.com/feed/", "TechCrunch"),
            ("hackernews_rss", "https://hnrss.org/frontpage", "Hacker News RSS"),
            ("bloomberg", "https://feeds.bloomberg.com/technology/news.rss", "Bloomberg Tech"),
            ("bbc_world", "https://feeds.bbci.co.uk/news/world/rss.xml", "BBC World"),
            ("lemonde_world", "https://www.lemonde.fr/en/international/rss_full.xml", "Le Monde International"),
            ("aljazeera_world", "https://www.aljazeera.com/xml/rss/all.xml", "Al Jazeera English"),
        ]

        async def fetch_feed(feed: tuple[str, str, str]):
            try:
                return await client.get_text(feed[1], retries=0, timeout=5.0)
            except Exception as exc:
                logger.debug("RSS feed %s unavailable: %s", feed[0], exc)
                return None

        bodies = await asyncio.gather(*(fetch_feed(feed) for feed in feeds))
        events_by_feed: list[list[RawEvent]] = []
        for (feed_id, _url, feed_name), xml in zip(feeds, bodies, strict=True):
            if xml is None:
                continue

            items = parse_feed(xml)
            feed_events: list[RawEvent] = []
            for rank, item in enumerate(items, start=1):
                title = item.get("title")
                link = item.get("link")
                if not title or not link:
                    continue

                link_digest = sha256(link.encode("utf-8", errors="ignore")).hexdigest()[:24]
                feed_events.append(
                    RawEvent(
                        source_id="rss_news",
                        external_id=f"{feed_id}:{link_digest}",
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
            if feed_events:
                events_by_feed.append(feed_events)

        # Round-robin so early feeds cannot consume the whole per-cycle quota.
        events: list[RawEvent] = []
        for rank in range(max((len(items) for items in events_by_feed), default=0)):
            for items in events_by_feed:
                if rank < len(items):
                    events.append(items[rank])
                    if len(events) >= ctx.limit:
                        return events
        if not events:
            raise SourceUnavailable("all RSS news feeds returned no items")
        return events


@register_source
class RssNewsAdapter(SourceAdapter):
    source_id = "rss_news"
    name = "Global RSS News (TechCrunch, HN, Bloomberg, BBC, Le Monde, Al Jazeera)"
    type = SourceType.NEWS
    description = (
        "Latest tech, startup, financial and international headlines from six public RSS feeds."
    )
    capabilities = ["news", "techcrunch", "hackernews", "bloomberg", "bbc_world", "lemonde", "aljazeera", "breaking_news", "startups"]
    priority = 27
    collect_interval_seconds = 60
    strategies = [RssNewsStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        cb = get_circuit_breaker(self.source_id)
        rl = get_rate_limiter(self.source_id)

        if cb.is_open():
            logger.warning("[%s] Circuit breaker is OPEN. Returning empty list gracefully.", self.source_id)
            return FetchResult(
                source_id=self.source_id,
                events=[],
                strategy="none",
                ok=True,
                notes="circuit open",
            )

        if not await rl.async_acquire():
            logger.warning("[%s] Rate limit exceeded. Returning empty list gracefully.", self.source_id)
            return FetchResult(
                source_id=self.source_id,
                events=[],
                strategy="none",
                ok=True,
                notes="rate limit exceeded",
            )

        result = await run_strategy_cascade(self, ctx, client)
        if result.ok and result.events:
            cb.record_success()
        else:
            cb.record_failure()
        return result
