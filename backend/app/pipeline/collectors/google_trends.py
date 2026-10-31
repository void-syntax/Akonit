"""Google Trends — Priority #2 signal source.

Verified public endpoint: https://trends.google.com/trending/rss?geo={CC}
Returns title, ht:approx_traffic, picture and related news items. The legacy
/trendingsearches/daily/rss path returns 404, so this is the supported feed.
No credentials, no paid tier, works for every country geo.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
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

ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S)
RE_TITLE = re.compile(r"<title>(.*?)</title>", re.S)
RE_TRAFFIC = re.compile(r"<ht:approx_traffic>(.*?)</ht:approx_traffic>", re.S)
RE_PICTURE = re.compile(r"<ht:picture>(.*?)</ht:picture>", re.S)
RE_PIC_SRC = re.compile(r"<ht:picture_source>(.*?)</ht:picture_source>", re.S)
RE_PUBDATE = re.compile(r"<pubDate>(.*?)</pubDate>", re.S)
RE_NEWS_TITLE = re.compile(r"<ht:news_item_title>(.*?)</ht:news_item_title>", re.S)
RE_NEWS_URL = re.compile(r"<ht:news_item_url>(.*?)</ht:news_item_url>", re.S)
RE_NEWS_SRC = re.compile(r"<ht:news_item_source>(.*?)</ht:news_item_source>", re.S)
RE_LINK = re.compile(r"<link>(.*?)</link>", re.S)

# Countries polled by default — broad coverage without hammering the feed.
DEFAULT_GEO: list[str] = [
    "US", "GB", "CA", "AU", "IN", "BR", "MX", "DE", "FR", "ES", "IT", "NL", "SE", "NO",
    "PL", "PT", "TR", "RU", "UA", "AE", "SA", "IL", "ZA", "NG", "KE", "EG", "MA",
    "KR", "JP", "CN", "TW", "HK", "SG", "MY", "TH", "VN", "ID", "PH", "AZ", "KZ",
    "AR", "CL", "CO", "PE", "NZ", "IE", "FI", "DK", "GR", "RO", "CZ", "HU", "RS",
]

TRAFFIC_RE = re.compile(r"([\d.]+)\s*([KMB]?)", re.I)
_REPEATED_CHAR = re.compile(r"(.)\1{4,}")
_URL_OR_HANDLE = re.compile(r"(?:https?://|www\.|@[\w.-]+)", re.I)
_SPAM_TERMS = re.compile(
    r"\b(?:watch\s+live|live\s+stream|free\s+stream|watch\s+online|"
    r"full\s+match|tv\s+channel|free\s+movie|click\s+here)\b",
    re.I,
)


def is_low_quality_trend(title: str) -> bool:
    """Reject obvious SEO/live-stream spam while keeping legitimate event names."""
    text = title.strip()
    if not text or len(text) > 180 or _URL_OR_HANDLE.search(text):
        return True
    if _REPEATED_CHAR.search(text):
        return True
    # RSS spam often repeats the same keyword to manipulate search ranking.
    words = re.findall(r"[\w'-]+", text.casefold())
    if len(words) >= 8 and len(set(words)) / len(words) < 0.55:
        return True
    if _SPAM_TERMS.search(text) and len(words) >= 7:
        return True
    # Ignore titles dominated by mathematical/ornamental Unicode alphabets,
    # a common way to evade keyword spam filters.
    letters = [char for char in text if char.isalpha()]
    ordinary_letters = [
        char for char in letters
        if char.isascii() or "LATIN" in unicodedata.name(char, "")
    ]
    if letters and len(ordinary_letters) / len(letters) < 0.65:
        return True
    suspicious_script_letters = [
        char for char in letters
        if "MATHEMATICAL" in unicodedata.name(char, "")
        or "FULLWIDTH" in unicodedata.name(char, "")
    ]
    if len(suspicious_script_letters) >= 4:
        return True
    return False


def parse_traffic(raw: str | None) -> float:
    """'500+' / '1M+' / '10K+' -> 500 / 1_000_000 / 10_000."""
    if not raw:
        return 0.0
    m = TRAFFIC_RE.search(raw.replace(",", ""))
    if not m:
        return 0.0
    try:
        value = float(m.group(1))
    except ValueError:
        return 0.0
    mult = {"": 1.0, "K": 1e3, "M": 1e6, "B": 1e9}.get(m.group(2).upper(), 1.0)
    return value * mult


def unescape(text: str) -> str:
    return (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .strip()
    )


def parse_pub_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    from email.utils import parsedate_to_datetime

    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None


class TrendingNowRssStrategy(Strategy):
    """Trending Now RSS per geo — free, no credentials, country-scoped."""

    name = "trending_rss"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        geos = ctx.countries or DEFAULT_GEO
        events: list[RawEvent] = []
        failures = 0
        failure_budget = max(3, len(geos) // 3)

        for geo in geos:
            url = f"https://trends.google.com/trending/rss?geo={geo}"
            try:
                xml = await client.get_text(url)
            except SourceUnavailable as exc:
                failures += 1
                logger.debug("trends geo=%s failed: %s", geo, exc)
                if failures >= failure_budget:
                    break
                continue

            events.extend(self._parse(xml, geo))
            if len(events) >= ctx.limit:
                break

        if not events:
            raise SourceUnavailable("no trends parsed from any geo")
        return events[: ctx.limit]

    def _parse(self, xml: str, geo: str) -> list[RawEvent]:
        events: list[RawEvent] = []
        for rank, block in enumerate(ITEM_RE.findall(xml), start=1):
            title_match = RE_TITLE.search(block)
            if not title_match:
                continue
            title = unescape(title_match.group(1))
            if not title or is_low_quality_trend(title):
                continue

            # Remove thin, uninformative items (1-2 word titles, noise words)
            title_words = title.strip().split()
            if len(title_words) < 2:
                continue
            if title.lower().strip() in ("test", "none", "null", "undefined", "foo", "bar"):
                continue

            traffic_raw = _grab(RE_TRAFFIC, block)
            traffic = parse_traffic(traffic_raw)
            news_titles = RE_NEWS_TITLE.findall(block)
            news_urls = RE_NEWS_URL.findall(block)
            news_sources = [unescape(s) for s in RE_NEWS_SRC.findall(block)]
            related = [
                {"title": unescape(t), "url": unescape(u)}
                for t, u in zip(news_titles, news_urls, strict=False)
            ]

            desc = related[0]["title"] if related else ""
            combined = f"{title} {desc}".lower()
            code_indicators = ["import ", "const ", "function(", "def ", "class ", "console.log", "=>", "<?php", "select * from"]
            if any(ind in combined for ind in code_indicators) and len(desc.strip()) < 30:
                continue

            if traffic < 200 and not related:
                continue

            slug = title.lower().replace(" ", "-")
            events.append(
                RawEvent(
                    source_id="google_trends",
                    external_id=f"gtrends:{geo}:{slug}",
                    title=title,
                    url=(
                        "https://trends.google.com/trends/explore?q="
                        f"{title.replace(' ', '%20')}&geo={geo}"
                    ),
                    description=related[0]["title"] if related else "",
                    activity=parse_traffic(traffic_raw),
                    activity_metric="approx_searches",
                    country_code=geo,
                    rank=rank,
                    thumbnail=_grab(RE_PICTURE, block),
                    category="search_trend",
                    published_at=parse_pub_date(_grab(RE_PUBDATE, block)),
                    metadata={
                        "traffic_raw": traffic_raw,
                        "picture_source": _grab(RE_PIC_SRC, block),
                        "related_news": related,
                        "news_sources": news_sources,
                        "geo": geo,
                    },
                )
            )
        return events


def _grab(pattern: re.Pattern[str], block: str) -> str | None:
    m = pattern.search(block)
    return unescape(m.group(1)) if m else None


@register_source
class GoogleTrendsAdapter(SourceAdapter):
    source_id = "google_trends"
    name = "Google Trends"
    type = SourceType.TREND
    description = (
        "Trending Now feed per country: early breakout search demand with "
        "approx search volume and related news. Zero credentials."
    )
    capabilities = ["search_trend", "breakout", "country_geo", "related_news", "recency"]
    priority = 10
    collect_interval_seconds = 600
    strategies = [TrendingNowRssStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)
        return None
