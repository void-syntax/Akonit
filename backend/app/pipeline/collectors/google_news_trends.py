"""Google News trending queries — Priority #2 trend signal.

Verified: https://news.google.com/rss/search?q=when:6h+{query}&hl=en-US returns
a 55KB RSS document. The `when:` operator gives a precise recency window, which
makes this the sharpest free breakout detector available: a topic with many
articles published in the last hour is rising right now, not last week.

Queries are derived from the product taxonomy so this source produces trend
signals rather than a generic news dump.
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

logger = get_logger(__name__)

# Query seeds aligned with the taxonomy: trends users actually watch for.
QUERIES: list[str] = [
    "viral trend",
    "makeup trend",
    "skincare trend",
    "beauty trend",
    "fashion trend",
    "prank challenge",
    "meme trend",
    "viral product",
    "side hustle",
    "free AI tool",
    "open source AI",
    "new app",
    "AI agent",
    "TikTok trend",
]

# Recency windows, newest first. Small windows mean breakout, large mean stable.
WINDOWS = ["when:1h", "when:6h", "when:24h"]

LOCALE_BY_COUNTRY: dict[str, tuple[str, str]] = {
    "US": ("en-US", "US"), "GB": ("en-GB", "GB"), "DE": ("de", "DE"),
    "FR": ("fr", "FR"), "ES": ("es", "ES"), "IT": ("it", "IT"),
    "TR": ("tr", "TR"), "BR": ("pt-BR", "BR"), "MX": ("es-419", "MX"),
    "IN": ("en-IN", "IN"), "JP": ("ja", "JP"), "KR": ("ko", "KR"),
    "CN": ("zh-CN", "CN"), "AE": ("ar", "AE"), "RU": ("ru", "RU"),
}


class NewsRssStrategy(Strategy):
    name = "news_rss_when"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        from app.pipeline.collectors.rss_utils import parse_feed

        queries = ctx.keywords[:8] if ctx.keywords else QUERIES
        countries = ctx.countries or ["US"]
        events: list[RawEvent] = []
        failures = 0

        for country in countries[:3]:
            hl, gl = LOCALE_BY_COUNTRY.get(country, ("en-US", country))
            for window in WINDOWS:
                for query in queries[:5]:
                    url = (
                        "https://news.google.com/rss/search"
                        f"?q={window}+{query.replace(' ', '+')}"
                        f"&hl={hl}&gl={gl}&ceid={gl}:{hl.split('-')[0]}"
                    )
                    try:
                        xml = await client.get_text(url, retries=1)
                    except SourceUnavailable as exc:
                        failures += 1
                        logger.debug("news rss %r failed: %s", url, exc)
                        if failures >= 5:
                            return events or _raise()
                        continue

                    parsed = parse_feed(xml)
                    for rank, item in enumerate(parsed, start=1):
                        if not item["title"] or not item["link"]:
                            continue
                        events.append(
                            RawEvent(
                                source_id="google_news_trends",
                                external_id=(
                                    f"gnews:{country}:{window}:"
                                    f"{item['link'].rsplit('/', 1)[-1][:16]}"
                                ),
                                title=item["title"][:500],
                                url=item["link"],
                                description=(item["description"] or "")[:400],
                                activity=float(len(parsed)),
                                activity_metric="query_mentions",
                                country_code=country,
                                rank=rank,
                                category="news_trend",
                                hashtags=item["tags"],
                                published_at=item["published"],
                                metadata={
                                    "query": query,
                                    "window": window,
                                    "hl": hl,
                                    "gl": gl,
                                    "strategy": "news_rss_when",
                                },
                            )
                        )
                    if len(events) >= ctx.limit:
                        return events[: ctx.limit]

        if not events:
            raise SourceUnavailable("google news RSS returned no entries")
        return events[: ctx.limit]


def _raise() -> list[RawEvent]:
    raise SourceUnavailable("google news RSS returned no entries for any query")


@register_source
class GoogleNewsTrendsAdapter(SourceAdapter):
    source_id = "google_news_trends"
    name = "Google News Trends"
    type = SourceType.TREND
    description = (
        "Topic bursts detected through the `when:` recency operator. A topic "
        "with many articles in the last hour is rising now, which makes this "
        "the earliest free breakout signal available."
    )
    capabilities = ["news_trend", "breakout", "recency", "country_geo", "velocity"]
    priority = 6
    collect_interval_seconds = 1800
    strategies = [NewsRssStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)