"""Low-cost user-configured RSS/Atom feed collector."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.core.config import settings
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
from app.pipeline.collectors.rss_utils import parse_feed

logger = get_logger(__name__)

MAX_FEEDS = 10
MAX_ITEMS_PER_FEED = 20
MAX_FEED_BYTES = 2_000_000


def configured_feed_urls() -> list[str]:
    """Parse comma/line separated feeds, accepting only HTTP(S) URLs."""
    raw = settings.extra_rss_feeds.replace("\n", ",").split(",")
    urls: list[str] = []
    seen: set[str] = set()
    for value in raw:
        url = value.strip()
        if not url or url in seen:
            continue
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            continue
        if parsed.username or parsed.password:
            continue
        seen.add(url)
        urls.append(url)
    limit = min(max(settings.extra_rss_feed_limit, 0), MAX_FEEDS)
    return urls[:limit]


class ConfiguredFeedsStrategy(Strategy):
    name = "configured_rss_atom"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        urls = configured_feed_urls()
        if not urls:
            # An optional empty configuration is idle, not a broken source.
            return []

        events: list[RawEvent] = []
        failures = 0
        for feed_url in urls:
            try:
                response = await client.get(feed_url, retries=0)
                content_type = response.headers.get("content-type", "")
                if len(response.content) > MAX_FEED_BYTES:
                    raise SourceUnavailable("feed exceeds the 2 MB size limit")
                if response.status_code != 200:
                    raise SourceUnavailable(f"feed returned HTTP {response.status_code}")
                xml = response.text
            except Exception as exc:
                failures += 1
                logger.info("configured RSS feed failed (%s)", type(exc).__name__)
                continue

            items = parse_feed(xml)[:MAX_ITEMS_PER_FEED]
            host = urlparse(feed_url).hostname or "feed"
            for rank, item in enumerate(items, start=1):
                title = item.get("title")
                link = item.get("link")
                if not title or not link:
                    continue
                events.append(
                    RawEvent(
                        source_id="custom_rss",
                        external_id=f"rss:{host}:{link}",
                        title=str(title)[:500],
                        url=str(link)[:2000],
                        description=str(item.get("description") or "")[:1200],
                        activity=0.0,
                        activity_metric="feed_mentions",
                        country_code=ctx.countries[0] if ctx.countries else None,
                        rank=rank,
                        category="custom_feed",
                        hashtags=(item.get("tags") or [])[:20],
                        published_at=item.get("published"),
                        metadata={
                            "feed_host": host,
                            "content_type": content_type[:100],
                            "strategy": self.name,
                        },
                    )
                )
                if len(events) >= ctx.limit:
                    return events[:ctx.limit]

        if not events:
            message = (
                "all configured RSS/Atom feeds failed"
                if failures == len(urls)
                else "configured RSS/Atom feeds contain no parseable items"
            )
            raise SourceUnavailable(message)
        return events[:ctx.limit]


@register_source
class CustomRssAdapter(SourceAdapter):
    source_id = "custom_rss"
    name = "Custom RSS / Atom Feeds"
    type = SourceType.NEWS
    description = (
        "User-configured public RSS 2.0, RSS 1.0/RDF, or Atom feeds. "
        "Up to ten feeds, fetched serially with 2 MB response limits."
    )
    capabilities = ["rss", "atom", "custom_sources", "news"]
    priority = 24
    cost = "FREE"
    credentials_required = False
    collect_interval_seconds = 900
    strategies = [ConfiguredFeedsStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)
