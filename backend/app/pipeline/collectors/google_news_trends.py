"""Google News trending queries — Priority #2 trend signal.

The `when:1h` operator keeps results recent. Queries and countries rotate on
each scheduled pass so the collector covers more topics instead of returning
early with a batch from just one search.

Queries are derived from the product taxonomy so this source produces trend
signals rather than a generic news dump.
"""

from __future__ import annotations

import hashlib
import asyncio
import time
from urllib.parse import quote_plus
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
    "breaking world news", "election policy", "public health research",
    "climate energy breakthrough", "cybersecurity vulnerability", "crypto market",
    "war OR conflict OR ceasefire", "economy OR inflation OR central bank",
    "merger OR layoffs OR company earnings", "cyberattack OR data breach OR vulnerability",
    "product recall OR supply chain OR shortage", "drug approval OR clinical trial OR outbreak",
    "earthquake OR wildfire OR flood", "court ruling OR regulation OR antitrust",
    "sports championship OR transfer", "entertainment OR celebrity OR film release",
    "startup funding", "consumer technology launch", "gaming industry trend",
    "science discovery", "creator economy", "viral product", "new trend",
    "AI agent", "open source AI", "free AI tool", "TikTok trend",
    "fashion trend", "skincare trend", "beauty trend", "music trend",
    "electric vehicle", "space launch", "food trend",
]


def _queries_for_cycle(custom_queries: list[str], cycle: int) -> list[str]:
    """Reserve most searches for broad discovery while rotating user interests.

    Replacing the taxonomy seeds with profile tags made this source silently
    collapse to only a few topics (often AI/beauty/fashion). One of each three
    slots follows user interests; the other two continue scanning the wider web.
    """
    custom: list[str] = []
    seen: set[str] = set()
    for query in custom_queries:
        clean = " ".join(str(query).split())
        key = clean.casefold()
        if (len(clean) >= 3 or (len(clean) == 2 and clean.isupper())) and key not in seen:
            custom.append(clean)
            seen.add(key)

    broad = [query for query in QUERIES if query.casefold() not in seen]
    selected: list[str] = []
    if custom:
        selected.append(custom[cycle % len(custom)])
    broad_start = (cycle * 2) % len(broad)
    for offset in range(min(2, len(broad))):
        query = broad[(broad_start + offset) % len(broad)]
        if query.casefold() not in {item.casefold() for item in selected}:
            selected.append(query)

    if len(selected) < 3:
        for offset in range(len(QUERIES)):
            query = QUERIES[(broad_start + offset) % len(QUERIES)]
            if query.casefold() not in {item.casefold() for item in selected}:
                selected.append(query)
                if len(selected) == 3:
                    break
    return selected

# Recency windows, newest first. Small windows mean breakout, large mean stable.
def _query_activity_metric(country: str, window: str, query: str) -> str:
    """Keep result-count trend math scoped to an identical search definition."""
    query_key = " ".join(query.casefold().split())
    identity = f"{country.upper()}\0{window.lower()}\0{query_key}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"gnews_{digest}"

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

        # The worker checks due sources every minute. Rotate three searches per
        # pass: one user interest (when configured) plus two broad topics.
        cycle = int(time.time() // 60)
        queries = _queries_for_cycle(ctx.keywords, cycle)
        country_pool = ctx.countries or ["US"]
        countries = [country_pool[cycle % len(country_pool)]]
        window = "when:1h"
        requests: list[tuple[str, str, str, str]] = []
        for country in countries:
            hl, gl = LOCALE_BY_COUNTRY.get(country, ("en-US", country))
            for query in queries:
                url = (
                    "https://news.google.com/rss/search"
                    f"?q={window}+{quote_plus(query)}"
                    f"&hl={hl}&gl={gl}&ceid={gl}:{hl.split('-')[0]}"
                )
                requests.append((country, query, hl, url))

        responses = await asyncio.gather(
            *(
                client.get_text(url, retries=0, timeout=6.0)
                for _, _, _, url in requests
            ),
            return_exceptions=True,
        )
        events: list[RawEvent] = []
        seen_urls: set[str] = set()
        per_query_limit = max(1, ctx.limit // max(len(requests), 1))
        failures = 0
        for (country, query, hl, _), xml in zip(requests, responses, strict=True):
            if isinstance(xml, BaseException):
                failures += 1
                continue
            parsed = parse_feed(xml)
            query_events = 0
            for rank, item in enumerate(parsed, start=1):
                title = str(item.get("title") or "").strip()
                url = str(item.get("link") or "").strip()
                if not title or not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                digest = hashlib.sha256(url.encode("utf-8", errors="ignore")).hexdigest()[:24]
                events.append(
                    RawEvent(
                        source_id="google_news_trends",
                        external_id=f"gnews:{digest}",
                        title=title[:500],
                        url=url,
                        description=(item.get("description") or "")[:400],
                        # A capped RSS result count is not a real activity metric.
                        activity=0.0,
                        activity_metric="news_mentions",
                        country_code=country,
                        rank=rank,
                        category="news_trend",
                        hashtags=item.get("tags", []),
                        published_at=item.get("published"),
                        metadata={
                            "query": query,
                            "window": window,
                            "hl": hl,
                            "gl": LOCALE_BY_COUNTRY.get(country, ("en-US", country))[1],
                            "strategy": "news_rss_when",
                        },
                    )
                )
                query_events += 1
                if query_events >= per_query_limit:
                    break

        if not events:
            if failures:
                raise SourceUnavailable("all Google News query requests failed")
            raise SourceUnavailable("google news RSS returned no entries")
        return events[: ctx.limit]


@register_source
class GoogleNewsTrendsAdapter(SourceAdapter):
    source_id = "google_news_trends"
    name = "Google News Trends"
    type = SourceType.TREND
    description = (
        "Rotating one-hour news searches across global topics and locales. "
        "Headlines stay unconfirmed until independent sources corroborate them."
    )
    capabilities = ["news_trend", "breakout", "recency", "country_geo", "velocity"]
    priority = 6
    collect_interval_seconds = 60
    strategies = [NewsRssStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)
