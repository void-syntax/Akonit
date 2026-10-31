"""X / Twitter trends — Priority #1 social source.

Verified public path: https://trends24.in/{country-slug}/ returns a public
aggregation page with per-hour / per-day / per-week trend cards, tweet counts
and search links. This third-party data is only a proxy for X trends. Other endpoints we tested:
  * x.com/i/api/2/guide.json               -> 403
  * api.twitter.com/1.1/trends/place.json -> 400
The adapter uses the public aggregation page and does not claim complete X coverage.

Slug mapping matters: trends24 has /japan/ and /united-states/ but no
/south-korea/ page, so aliases are mapped explicitly.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote_plus

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

logger = get_logger(__name__)

CARD_SPLIT_RE = re.compile(r"class=[\"'][^\"']*trend-card__list[^\"']*[\"']")

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

# Keep a useful fallback even when the profile is narrowed to a region that
# Trends24 does not currently publish. These are public aggregate pages, not
# a claim of complete X coverage.
FALLBACK_COUNTRIES = ("US", "GB", "JP")


class _TrendListParser(HTMLParser):
    """Extract X trend anchors from both old cards and newer timeline lists."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[tuple[str, str, str]] = []
        self._item: dict[str, Any] | None = None
        self._anchor_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "li":
            self._item = {"href": "", "anchor": [], "text": []}
            self._anchor_depth = 0
        elif tag == "a" and self._item is not None:
            self._item["href"] = attributes.get("href") or ""
            self._anchor_depth += 1

    def handle_data(self, data: str) -> None:
        if self._item is None:
            return
        self._item["text"].append(data)
        if self._anchor_depth:
            self._item["anchor"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._item is not None:
            self._anchor_depth = max(self._anchor_depth - 1, 0)
        elif tag == "li" and self._item is not None:
            self.items.append(
                (
                    str(self._item["href"]),
                    " ".join(self._item["anchor"]).strip(),
                    " ".join(self._item["text"]).strip(),
                )
            )
            self._item = None


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




class PublicTrendsPageStrategy(Strategy):
    """Parses trends24.in public trend cards (no credentials required)."""

    name = "trends24_public"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        events: list[RawEvent] = []
        parsed_any = False

        requested = ctx.countries or settings.default_collect_countries
        countries = [c for c in requested if c in SLUG_MAP]
        if not countries:
            countries = [c for c in settings.default_collect_countries if c in SLUG_MAP]
        if countries:
            # Rotate three light public pages per five-minute pass.
            slot = int(datetime.now(UTC).timestamp() // 1200) % len(countries)
            countries = [
                countries[(slot + i) % len(countries)]
                for i in range(min(3, len(countries)))
            ]
        base_quota, extra = divmod(ctx.limit, max(len(countries), 1))
        attempted: list[str] = []
        for index, country in enumerate(countries):
            attempted.append(country)
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
                quota = base_quota + int(index < extra)
                events.extend(parsed[: max(quota, 1)])

        if not parsed_any:
            # Some countries have a slug but no live Trends24 page. Retry one
            # broadly available locale, and label those events with that real
            # locale instead of pretending they came from the requested region.
            fallback_order = [
                *settings.default_collect_countries,
                *FALLBACK_COUNTRIES,
            ]
            fallback_country = next(
                (
                    country
                    for country in fallback_order
                    if country in SLUG_MAP and country not in attempted
                ),
                None,
            )
            if fallback_country:
                try:
                    html = await client.get_text(
                        f"https://trends24.in/{SLUG_MAP[fallback_country]}/",
                        retries=0,
                        timeout=8.0,
                    )
                except SourceUnavailable as exc:
                    logger.debug("x trends fallback %s failed: %s", fallback_country, exc)
                else:
                    events.extend(self._parse(html, fallback_country)[: ctx.limit])
                    parsed_any = bool(events)

        if not parsed_any:
            raise SourceUnavailable(
                f"no trend cards parsed for locales: {', '.join(attempted) or 'none'}"
            )
        return events[: ctx.limit]

    def _parse(self, html: str, country: str) -> list[RawEvent]:
        cards = CARD_SPLIT_RE.split(html)
        events: list[RawEvent] = []

        card_windows = cards[1:4] if len(cards) > 1 else [html]
        for window_idx, card in enumerate(card_windows, start=1):
            label = (
                WINDOW_LABELS[window_idx - 1]
                if window_idx <= len(WINDOW_LABELS)
                else f"{window_idx}h"
            )
            parser = _TrendListParser()
            parser.feed(card)
            for rank, (href, name, row_text) in enumerate(parser.items, start=1):
                if not re.search(
                    r"(?:twitter\.com|x\.com)|(?:^|/)search(?:\?|$)",
                    href,
                    re.I,
                ):
                    continue
                count_match = re.search(r"\b([\d,.]+\s*[KMB]?)\b", row_text)
                count_raw = count_match.group(1) if count_match else ""
                if not name:
                    continue
                clean = name.lstrip("#")
                x_url = (
                    href
                    if re.match(r"https?://(?:www\.)?(?:twitter\.com|x\.com)/", href, re.I)
                    else f"https://x.com/search?q={quote_plus(clean)}"
                )
                events.append(
                    RawEvent(
                        source_id="x_trends",
                        external_id=f"xt:{country}:{window_idx}:{clean.lower()}",
                        title=name if name.startswith("#") else f"#{name}",
                        url=x_url,
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


@register_source
class XTrendsAdapter(SourceAdapter):
    source_id = "x_trends"
    name = "X (Twitter) Trends"
    type = SourceType.SOCIAL
    description = (
        "Topics listed by the public trends24 aggregation. Third-party coverage "
        "may vary and is not a direct or complete feed of X posts."
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
    # Trends have a useful lifetime of minutes, and the public page is a
    # lightweight single request on a five-minute cadence.
    collect_interval_seconds = 300
    strategies = [PublicTrendsPageStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)


def slug_of(href: str | None) -> str | None:
    if not href:
        return None
    m = re.search(r"q=([^&]+)", href)
    return m.group(1) if m else None
