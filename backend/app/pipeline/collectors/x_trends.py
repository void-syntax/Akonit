"""X / Twitter trends — Priority #1 social source.

Verified public path: https://trends24.in/{country-slug}/ returns a public
aggregation page with per-hour / per-day / per-week trend cards, tweet counts
and search links. Other endpoints we tested:
  * x.com/i/api/2/guide.json               -> 403
  * api.twitter.com/1.1/trends/place.json -> 400
So the public trends page is the primary strategy.

Slug mapping matters: trends24 has /japan/ and /united-states/ but no
/south-korea/ page, so aliases are mapped explicitly.
"""

from __future__ import annotations

import re
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

TREND_ROW_RE = re.compile(
    r'<li>\s*<span class=trend-name>\s*<a href="([^"]+)"[^>]*>([^<]+)</a>'
    r"\s*(?:<span class=tweet-count[^>]*>([^<]*)</span>)?",
    re.S,
)
CARD_SPLIT_RE = re.compile(r"class=trend-card__list")

# country code -> trends24 slug (verified against live pages)
SLUG_MAP: dict[str, str] = {
    "US": "united-states", "GB": "united-kingdom", "KR": "korea",
    "JP": "japan", "CN": "china", "TW": "taiwan", "HK": "hong-kong",
    "IN": "india", "BR": "brazil", "MX": "mexico", "DE": "germany",
    "FR": "france", "ES": "spain", "IT": "italy", "CA": "canada",
    "AU": "australia", "RU": "russia", "TR": "turkey",
    "AE": "united-arab-emirates", "SA": "saudi-arabia", "IL": "israel",
    "ZA": "south-africa", "NG": "nigeria", "EG": "egypt",
    "KZ": "kazakhstan", "AZ": "azerbaijan", "AR": "argentina",
    "PL": "poland", "NL": "netherlands", "SE": "sweden", "PT": "portugal",
    "ID": "indonesia", "PH": "philippines", "TH": "thailand",
    "VN": "vietnam", "MY": "malaysia", "SG": "singapore",
    "IR": "iran", "PK": "pakistan", "BD": "bangladesh",
    "CO": "colombia", "CL": "chile", "PE": "peru", "NZ": "new-zealand",
    "IE": "ireland", "UA": "ukraine", "RO": "romania", "GR": "greece",
}

# Page windows, most recent first — index gives an extra growth dimension.
WINDOW_LABELS = ["1h", "3h", "6h", "12h", "24h", "1d", "1w"]


def parse_tweet_count(text: str | None) -> float:
    if not text:
        return 0.0
    t = text.strip().replace(",", "")
    m = re.match(r"([\d.]+)\s*([KMB]?)", t)
    if not m:
        return 0.0
    try:
        value = float(m.group(1))
    except ValueError:
        return 0.0
    return value * {"": 1.0, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2).upper()]


def slug_of(href: str | None) -> str | None:
    if not href:
        return None
    m = re.search(r"q=([^&]+)", href)
    return m.group(1) if m else None


class PublicTrendsPageStrategy(Strategy):
    """Parses trends24.in public trend cards (no credentials required)."""

    name = "trends24_public"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        events: list[RawEvent] = []
        parsed_any = False

        for country in (ctx.countries or list(SLUG_MAP)[:12]):
            slug = SLUG_MAP.get(country)
            if not slug:
                continue
            try:
                html = await client.get_text(
                    f"https://trends24.in/{slug}/", retries=1
                )
            except SourceUnavailable as exc:
                logger.debug("x trends %s failed: %s", country, exc)
                continue

            parsed = self._parse(html, country)
            if parsed:
                parsed_any = True
                events.extend(parsed)
            if len(events) >= ctx.limit:
                break

        if not parsed_any:
            raise SourceUnavailable("no trend cards parsed from trends24 pages")
        return events[: ctx.limit]

    def _parse(self, html: str, country: str) -> list[RawEvent]:
        cards = CARD_SPLIT_RE.split(html)
        events: list[RawEvent] = []

        for window_idx, card in enumerate(cards[1:4], start=1):
            label = (
                WINDOW_LABELS[window_idx - 1]
                if window_idx <= len(WINDOW_LABELS)
                else f"{window_idx}h"
            )
            for rank, m in enumerate(TREND_ROW_RE.finditer(card), start=1):
                href, name, count_raw = m.group(1), m.group(2).strip(), m.group(3)
                if not name:
                    continue
                clean = name.lstrip("#")
                events.append(
                    RawEvent(
                        source_id="x_trends",
                        external_id=f"xt:{country}:{window_idx}:{clean.lower()}",
                        title=name if name.startswith("#") else f"#{name}",
                        url=href or f"https://x.com/search?q={clean}",
                        description=f"Trending on X in {country} ({label} window)",
                        activity=parse_tweet_count(count_raw),
                        activity_metric="posts",
                        country_code=country,
                        rank=rank,
                        category="trend",
                        hashtags=[clean],
                        metadata={
                            "window": label,
                            "window_index": window_idx,
                            "posts_text": (count_raw or "").strip(),
                            "query": slug_of(href),
                            "strategy": "trends24_public",
                        },
                    )
                )
        return events


class OfficialApiStrategy(Strategy):
    """Official X API — kept for when an approved tier is configured."""

    name = "official_api"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        raise SourceUnavailable(
            "X API v1.1 trends/place requires an approved paid tier; the "
            "trends24_public strategy already provides free coverage"
        )


@register_source
class XTrendsAdapter(SourceAdapter):
    source_id = "x_trends"
    name = "X (Twitter) Trends"
    type = SourceType.SOCIAL
    description = (
        "Trending topics and hashtags per country from the public trends24 "
        "aggregation, including hour/day/week windows that make growth "
        "measurable without any paid API."
    )
    capabilities = [
        "trending",
        "hashtags",
        "memes",
        "breaking",
        "country_geo",
        "windows",
    ]
    priority = 4
    collect_interval_seconds = 1200
    strategies = [PublicTrendsPageStrategy(), OfficialApiStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)


def slug_of(href: str | None) -> str | None:
    if not href:
        return None
    m = re.search(r"q=([^&]+)", href)
    return m.group(1) if m else None