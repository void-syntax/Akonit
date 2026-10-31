"""TikTok — CRITICAL PRIORITY #1 source.

Research findings (verified against the live site):
  * Public tag pages (https://www.tiktok.com/tag/{tag}) return ~380KB HTML that
    embeds `__UNIVERSAL_DATA_FOR_REHYDRATION__` JSON with challenge stats
    (viewCount / videoCount / statsV2). This is publicly rendered page data —
    no login, no CAPTCHA, no anti-bot bypass.
  * The token-gated Creative Center endpoint is not the documented Research or
    Commercial Content API; its availability depends on TikTok permissions.
  * The approved Commercial Content API is implemented as a separate adapter
    in `tiktok_commercial.py` and currently covers European commercial content.

Parsing is defensive and key-based (never positional) so a site redesign
degrades to DEGRADED instead of crashing the pipeline.
"""

from __future__ import annotations

import json
import re
from typing import Any

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

REHYDRATION_RE = re.compile(
    r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', re.S
)
SIGI_STATE_RE = re.compile(r'<script id="SIGI_STATE"[^>]*>(.*?)</script>', re.S)
OG_TITLE_RE = re.compile(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', re.I)
OG_IMAGE_RE = re.compile(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', re.I)
OG_DESC_RE = re.compile(r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"', re.I)

# Hashtag seeds covering the categories Signal Radar cares about most.
# The worker rotates through them so collection stays affordable and diverse.
DEFAULT_TAG_SEEDS: list[str] = [
    "trending", "viral", "memes", "challenges", "pranks",
    "aivideo", "chatgpt", "tech", "gadgets", "opensource",
    "crypto", "investing", "startups", "smallbusiness", "sidehustle",
    "gaming", "fitness", "wellness", "foodtok", "travel",
    "climate", "science", "education", "music", "fashion",
    "beauty", "makeup", "skincare", "hair", "nails",
    "viralproducts", "tiktokmademebuyit", "trendingaudio",
]

COUNTRY_TAGS: dict[str, list[str]] = {
    "US": ["trending", "viral", "fyp"],
    "GB": ["trending", "tiktokmademebuyit"],
    "KR": ["kbeauty", "koreanmakeup", "kbeautytrend"],
    "JP": ["makeup", "skin_care"],
    "TR": ["tiktoktrend", "güzel"],
    "AE": ["dubai", "tiktoktrends"],
    "AZ": ["aztrends"],
    "BR": ["tiktokbrasil", "beleza"],
    "IN": ["trending", "viral"],
    "FR": ["tiktokfrance"],
    "DE": ["tiktokdeutschland"],
    "ID": ["tiktokindonesia"],
    "MX": ["tiktokmexico"],
}


def _walk(node: Any) -> Any:
    """Yield every nested dict/list node of an arbitrary JSON structure."""
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            yield current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def find_challenge_payloads(data: Any) -> list[dict]:
    """Extract hashtag/challenge records regardless of TikTok's internal shape."""
    out: list[dict] = []
    for node in _walk(data):
        # A challenge record has a challengeName or the tag name plus stats
        name = (
            node.get("challengeName")
            or node.get("hashtagName")
            or node.get("title")
        )
        if not isinstance(name, str) or not name.strip():
            continue
        stats = node.get("statsV2") or node.get("stats") or {}
        view_count = _pick_int(
            node.get("viewCount"),
            node.get("videoCount"),
            stats.get("viewCount"),
            stats.get("videoCount"),
            stats.get("vv"),
        )
        if view_count is None:
            continue
        out.append(
            {
                "name": name.strip(),
                "view_count": float(view_count),
                "video_count": _pick_int(node.get("videoCount"), stats.get("videoCount")),
                "rank": _pick_int(node.get("rank"), node.get("position")),
                "is_locked": bool(node.get("isLocked", False)),
                "payload": {
                    k: v
                    for k, v in node.items()
                    if isinstance(v, (str, int, float, bool)) and k != "challengeInfo"
                },
            }
        )
    return out


def _pick_int(*values: Any) -> int | None:
    for v in values:
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)) and v >= 0:
            return int(v)
        if isinstance(v, str) and v.isdigit():
            return int(v)
    return None
class PublicTagPageStrategy(Strategy):
    """Reads publicly rendered TikTok tag pages and parses the embedded JSON."""

    name = "public_tag_pages"

    def __init__(self) -> None:
        self._seed_offset = 0

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        events: list[RawEvent] = []
        parsed_any = False
        failures = 0

        seeds = self._seeds(ctx)
        if not seeds:
            raise SourceUnavailable("no TikTok tag seeds configured")
        batch_size = min(2, len(seeds))
        batch = [
            seeds[(self._seed_offset + offset) % len(seeds)]
            for offset in range(batch_size)
        ]
        self._seed_offset = (self._seed_offset + batch_size) % len(seeds)

        for tag in batch:
            url = f"https://www.tiktok.com/tag/{tag}"
            try:
                html = await client.get_text(url, retries=0, timeout=8.0)
            except SourceUnavailable as exc:
                failures += 1
                logger.debug("tiktok tag %s failed: %s", tag, exc)
                if failures >= batch_size:
                    break
                continue

            records = self._parse(html, tag, self._country_for_tag(ctx, tag))
            if records:
                parsed_any = True
                events.extend(records)
            if len(events) >= ctx.limit:
                break

        if not parsed_any:
            raise SourceUnavailable(
                "TikTok tag pages returned no parseable challenge data "
                "(layout changed or traffic was blocked)"
            )
        return events[: ctx.limit]

    def _seeds(self, ctx: FetchContext) -> list[str]:
        seeds: list[str] = []
        for country in ctx.countries or []:
            seeds.extend(COUNTRY_TAGS.get(country, []))
        seeds.extend(DEFAULT_TAG_SEEDS)
        seen: set[str] = set()
        ordered: list[str] = []
        for s in seeds:
            if s.lower() not in seen:
                seen.add(s.lower())
                ordered.append(s)
        return ordered[:60]

    def _country_for_tag(self, ctx: FetchContext, tag: str) -> str | None:
        tag_l = tag.lower()
        for country, tags in COUNTRY_TAGS.items():
            if tag_l in {t.lower() for t in tags}:
                return country
        return ctx.countries[0] if ctx.countries else None

    def _parse(self, html: str, tag: str, country: str | None) -> list[RawEvent]:
        data = _extract_json(html)
        records = find_challenge_payloads(data) if data else []
        og_image = _meta(OG_IMAGE_RE, html)
        og_desc = _meta(OG_DESC_RE, html)

        if not records:
            # A page title is not evidence of a trend. Do not turn the requested
            # seed itself into a zero-activity signal when TikTok omits stats.
            return []

        events: list[RawEvent] = []
        for rec in records[:5]:
            name = rec["name"]
            events.append(
                RawEvent(
                    source_id="tiktok",
                    external_id=f"tiktok:{name.lower().replace(' ', '')}",
                    title=f"#{name}",
                    url=f"https://www.tiktok.com/tag/{name.replace(' ', '')}",
                    description=f"TikTok hashtag #{name} with {int(rec['view_count']):,} views",
                    activity=float(rec["view_count"]),
                    activity_metric="view_count",
                    country_code=country,
                    rank=rec.get("rank"),
                    category="hashtag",
                    hashtags=[name],
                    thumbnail=og_image,
                    metadata={
                        "tag": name,
                        "video_count": rec.get("video_count"),
                        "stats_available": True,
                        "og_description": og_desc,
                        **rec["payload"],
                    },
                )
            )
        return events
def _extract_json(html: str) -> Any | None:
    for pattern in (REHYDRATION_RE, SIGI_STATE_RE):
        match = pattern.search(html)
        if not match:
            continue
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
    return None


def _meta(pattern: re.Pattern[str], html: str) -> str | None:
    m = pattern.search(html)
    if not m:
        return None
    return (
        m.group(1)
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .strip()
    )


class CreativeCenterApiStrategy(Strategy):
    """Token-gated Creative Center endpoint; availability depends on permissions."""

    name = "creative_center_api"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        token = settings.tiktok_api_token
        if not token:
            raise SourceUnavailable(
                "no TikTok app token configured; creative_radar_api answers "
                "40101 no permission without one"
            )

        events: list[RawEvent] = []
        for country in (ctx.countries or ["US"]):
            url = (
                "https://ads.tiktok.com/creative_radar_api/v1/popular_trend"
                f"/hashtag/list?period=7&country_code={country}&page=1&limit=20"
            )
            data = await client.get_json(
                url, headers={"Authorization": f"Bearer {token}"}
            )
            if not isinstance(data, dict) or data.get("code") not in (0, None):
                raise SourceUnavailable(f"creative center error: {data}")

            items = (data.get("data") or {}).get("hashtags") or []
            for rank, item in enumerate(items, start=1):
                name = item.get("hashtag_name") or item.get("challenge_name")
                if not name:
                    continue
                events.append(
                    RawEvent(
                        source_id="tiktok",
                        external_id=f"tiktok-cc:{country}:{str(name).lower()}",
                        title=f"#{name}",
                        url=f"https://www.tiktok.com/tag/{name}",
                        description=str(item.get("trend_desc") or "")[:400],
                        activity=float(item.get("video_views") or 0),
                        activity_metric="view_count",
                        country_code=country,
                        rank=rank,
                        category="hashtag",
                        hashtags=[str(name)],
                        metadata={"strategy": "creative_center", "raw": item},
                    )
                )
            if events:
                break
        if not events:
            raise SourceUnavailable("creative center returned no hashtags")
        return events[: ctx.limit]


@register_source
class TikTokAdapter(SourceAdapter):
    source_id = "tiktok"
    name = "TikTok"
    type = SourceType.SOCIAL
    description = (
        "Hashtag trends through the authorized Creative Center endpoint. Public "
        "tag pages currently challenge automated requests; no challenge bypass "
        "is attempted. Commercial Content API coverage is a separate source."
    )
    capabilities = [
        "hashtags",
        "viral_formats",
        "memes",
        "beauty",
        "regional",
        "country_geo",
        "views",
    ]
    priority = 1
    # Public tag pages now consistently serve an anti-bot challenge to the
    # collector. Do not retry that page parser every cycle; use the supported
    # Creative Center route only when an authorized token is configured.
    credentials_required = True
    collect_interval_seconds = 21600
    credentials_hint = (
        "TikTok's public tag pages currently return a challenge instead of "
        "trend data. Configure an authorized Creative Center token to enable "
        "hashtag trends; no challenge bypass is attempted."
    )
    strategies = [CreativeCenterApiStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)
