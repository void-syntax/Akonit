"""YouTube — Priority #1 social source.

Verified public paths:
  * https://www.youtube.com/feed/trending?hl=en&gl=US returns ~890KB HTML with
    `ytInitialData` containing trending videos (views, published time, channel).
  * https://www.youtube.com/feeds/videos.xml?channel_id=... returns public RSS.
  * Official Data API v3 answers 403 without a key, so it is a later strategy
    that activates automatically when YOUTUBE_API_KEY is configured.

Shorts are detected from the `lengthText` badge / "shorts" path segment.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
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

INITIAL_DATA_MARKERS = (
    "var ytInitialData = ",
    'window["ytInitialData"] = ',
    "ytInitialData = ",
)
RE_VIEWS = re.compile(r'"viewCountText":\{"simpleText":"(.*?)"\}')
RE_PUBLISHED = re.compile(r'"publishedTimeText":\{"simpleText":"(.*?)"\}')
RE_VIDEO_ID = re.compile(r'"videoId":"([\w-]{11})"')
RE_LENGTH = re.compile(r'"lengthText":\{"simpleText":"(.*?)"\}')
RE_CHANNEL = re.compile(r'"ownerText":\{"runs":\[\{"text":"(.*?)"')
RE_TITLE = re.compile(r'"title":\{"runs":\[\{"text":"(.*?)"')

DEFAULT_GEO: list[str] = ["US", "GB", "KR", "JP", "TR", "IN", "BR", "DE", "FR", "AE"]

# Search seeds. These must be *subjects* that people publish about, never the
# word "trending" itself: searching YouTube for "trending now" returns videos
# whose title happens to contain that phrase, which is how five-year-old
# re-uploads ended up in the feed looking like breaking news.
TRENDING_QUERIES: list[str] = [
    "viral challenge 2026",
    "new ai tool",
    "skincare routine",
    "dance trend",
]

# Tracked channels per niche — public RSS, no quota cost.
TRACKED_CHANNELS: dict[str, str] = {
    "mkbhd": "UC_x5XG1OV2P6uZZ5FSM9Ttw",
    "veritasium": "UCHnyfMqiRRG1u-2MsSQLbXA",
    "marques": "UCmU0i5b0K4tqfB3iy2v0TA",
    "google_developers": "UC_x5XG1OV2P6uZZ5FSM9Ttw",
}


def _clean(text: str) -> str:
    return (
        text.replace("\\u0026", "&")
        .replace('\\"', '"')
        .replace("\\u003c", "<")
        .replace("\\u003e", ">")
        .replace("\\n", " ")
        .strip()
    )


def parse_view_text(text: str) -> float:
    """'1.2M views' / '345,678 views' -> 1200000.0 / 345678.0"""
    if not text:
        return 0.0
    t = text.lower().replace(",", "")
    num = re.match(r"([\d.]+)", t)
    if not num:
        return 0.0
    try:
        value = float(num.group(1))
    except ValueError:
        return 0.0
    if "m" in t[: num.end() + 1]:
        value *= 1e6
    elif "k" in t[: num.end() + 1]:
        value *= 1e3
    return value


def is_short(length_text: str | None, url_path: str | None = None) -> bool:
    if url_path and "/shorts/" in url_path:
        return True
    if not length_text:
        return False
    m = re.match(r"(\d+):(\d{2})", length_text.strip())
    if not m:
        return False
    minutes, seconds = int(m.group(1)), int(m.group(2))
    return minutes == 0 and seconds <= 60


def parse_relative_time(text: str | None) -> datetime | None:
    """Turn YouTube's relative age into a timestamp.

    YouTube abbreviates aggressively: '8mo ago', '3d ago', '14h ago', with no
    space between the number and the unit. The previous pattern required
    whitespace, so it matched almost nothing and every video came back undated —
    which is precisely why five-year-old uploads were treated as fresh.
    """
    if not text:
        return None
    from datetime import timedelta

    # Abbreviations first ('8mo', '3d'), then the long form ('8 months ago').
    # Longer alternatives come first so 'mo' is not shadowed by 'm'. No trailing
    # word boundary: it would reject '45s ago', because 's' is not a word
    # character and therefore never has a boundary right after it.
    m = re.search(
        r"(\d+)\s*(seconds?|minutes?|months?|weeks?|years?|hours?|secs?|mins?|hrs?|mos?|[dsmwyh])",
        text.lower(),
    )
    if not m:
        return None
    amount = int(m.group(1))
    raw_unit = m.group(2).lower()
    # Collapse every abbreviation YouTube emits onto one canonical unit name.
    # Listing the plural short forms explicitly avoids stripping them into an
    # unknown token ('hrs' must not degrade to 'hr' via a blind rstrip).
    unit = {
        "s": "second", "sec": "second", "secs": "second",
        "min": "minute", "mins": "minute",
        "h": "hour", "hr": "hour", "hrs": "hour",
        "d": "day", "days": "day",
        "w": "week", "weeks": "week",
        "mo": "month", "mos": "month",
        "y": "year", "years": "year",
        "second": "second", "seconds": "second",
        "minute": "minute", "minutes": "minute",
        "hour": "hour", "hours": "hour",
        "month": "month", "months": "month",
        "week": "week", "year": "year",
    }.get(raw_unit)
    if unit is None:
        return None

    delta = {
        "second": timedelta(seconds=amount),
        "minute": timedelta(minutes=amount),
        "hour": timedelta(hours=amount),
        "day": timedelta(days=amount),
        "week": timedelta(weeks=amount),
        "month": timedelta(days=30 * amount),
        "year": timedelta(days=365 * amount),
    }[unit]
    return datetime.now().astimezone() - delta


def extract_initial_data(html: str) -> str | None:
    """Return the ytInitialData JSON substring using balanced-brace scanning."""
    for marker in INITIAL_DATA_MARKERS:
        idx = html.find(marker)
        if idx < 0:
            continue
        start = html.find("{", idx + len(marker))
        if start < 0:
            continue
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, min(len(html), start + 4_000_000)):
            ch = html[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return html[start : i + 1]
    return None


def _shorts_published_text(renderer: dict[str, Any]) -> str | None:
    """Publication age for a shortsLockupViewModel, when it exposes one.

    Shorts carry no publishedTimeText, and their overlay primaryText is the
    caption rather than a relative time, so there is genuinely no date to read.
    Returning None here is honest: the caller marks such items as undated so the
    freshness filter can treat them separately instead of guessing an age.
    """
    return None


class SearchResultsStrategy(Strategy):
    """Trending via public search results sorted by upload date.

    Research note: /feed/trending now renders an anonymous 'feedNudgeRenderer'
    placeholder with zero videos (verified live). The public search results
    page does return full video renderers — videoId, viewCountText,
    publishedTimeText — and also shortsLockupViewModel entries, so it is the
    working free path for trending + Shorts.
    """

    name = "search_sorted"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        events: list[RawEvent] = []
        parsed_any = False
        queries = ctx.keywords[:3] if ctx.keywords else TRENDING_QUERIES

        for geo in (ctx.countries or DEFAULT_GEO):
            for query in queries:
                url = (
                    "https://www.youtube.com/results?search_query="
                    f"{query.replace(' ', '+')}&sp=CAI%253D&hl=en&gl={geo}"
                )
                try:
                    html = await client.get_text(url, retries=1)
                except SourceUnavailable as exc:
                    logger.debug("youtube search geo=%s q=%r failed: %s", geo, query, exc)
                    continue

                parsed = self._parse(html, geo)
                if parsed:
                    parsed_any = True
                    events.extend(parsed)
                if len(events) >= ctx.limit:
                    return events[: ctx.limit]
            if events:
                break

        if not parsed_any:
            raise SourceUnavailable(
                "ytInitialData from search results contained no video renderers"
            )
        return events[: ctx.limit]

    def _parse(self, html: str, geo: str) -> list[RawEvent]:
        raw = extract_initial_data(html)
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.debug("ytInitialData invalid JSON: %s", exc)
            return []

        events: list[RawEvent] = []
        seen: set[str] = set()
        for node in walk_json(parsed):
            event = self._event_from_node(node, geo, seen)
            if not event:
                continue
            # Shorts expose no publication date, so their age is unknowable.
            # Letting them through would put undated results into a feed whose
            # entire promise is freshness, so only dated items are kept.
            if event.published_at is None:
                continue
            events.append(event)
            if len(events) >= 30:
                break
        return events

    def _event_from_node(
        self, node: dict[str, Any], geo: str, seen: set[str]
    ) -> RawEvent | None:
        renderer = node.get("videoRenderer") or node.get("shortsLockupViewModel")
        if not isinstance(renderer, dict):
            return None

        video_id = renderer.get("videoId")
        entity_id = renderer.get("entityId")
        if not video_id and isinstance(entity_id, str):
            video_id = entity_id.removeprefix("shorts-lockup-v1_")
        if not isinstance(video_id, str) or len(video_id) != 11:
            return None
        if video_id in seen:
            return None
        seen.add(video_id)

        title = _text(renderer.get("title"))
        if not title:
            return None
        views_text = _text(renderer.get("viewCountText")) or _text(
            renderer.get("viewCountTextShort")
        )
        published_text = (
            _text(renderer.get("publishedTimeText"))
            or _text(renderer.get("publishedTimeTextShort"))
            or _shorts_published_text(renderer)
        )
        length_text = _text(renderer.get("lengthText"))
        owner = (
            _text(renderer.get("ownerText"))
            or _text(renderer.get("shortBylineText"))
            or _text(renderer.get("longBylineText"))
            or _text(renderer.get("channelName"))
        )
        thumb = _thumbnail(renderer)

        short = "shortsLockupViewModel" in node or is_short(length_text)
        published_at = parse_relative_time(published_text)
        return RawEvent(
            source_id="youtube",
            external_id=f"yt:{video_id}",
            title=title,
            url=f"https://www.youtube.com/watch?v={video_id}",
            description=f"{owner} - {title}"[:400] if owner else title[:400],
            activity=parse_view_text(views_text or ""),
            activity_metric="views",
            country_code=geo,
            category="short" if short else "video",
            published_at=published_at,
            thumbnail=thumb or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            metadata={
                "video_id": video_id,
                "channel": owner,
                "views_text": views_text,
                "length_text": length_text,
                "published_text": published_text,
                # Search results mix Shorts with full videos, and only full
                # videos expose a publication date. Flagging that lets the
                # freshness filter reject undated results instead of treating
                # an unknown age as "brand new".
                "dated": published_at is not None,
                "is_short": short,
                "geo": geo,
                "strategy": "search_sorted",
            },
        )


def _text(node: Any) -> str | None:
    """YouTube text nodes come as {simpleText} or {runs:[{text}]}."""
    if not isinstance(node, dict):
        return None
    if isinstance(node.get("simpleText"), str):
        return _clean(node["simpleText"])
    runs = node.get("runs")
    if isinstance(runs, list):
        joined = "".join(
            r.get("text", "") for r in runs if isinstance(r, dict)
        )
        return _clean(joined) or None
    if isinstance(node.get("content"), str):
        return _clean(node["content"])
    return None


def _thumbnail(renderer: dict[str, Any]) -> str | None:
    for key in ("thumbnail", "thumbnailViewModel"):
        node = renderer.get(key)
        if isinstance(node, dict):
            node = node.get("thumbnails")
        if isinstance(node, list) and node:
            last = node[-1]
            if isinstance(last, dict):
                return last.get("url") or last.get("imageUrl")
    return None


def walk_json(node: Any):
    """Yield every nested dict of an arbitrary JSON structure."""
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            yield current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


class ChannelRssStrategy(Strategy):
    """Public channel feeds — new uploads surface fast, zero quota."""

    name = "channel_rss"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        from app.pipeline.collectors.rss_utils import parse_atom_feed

        events: list[RawEvent] = []
        for channel_id in TRACKED_CHANNELS.values():
            url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            try:
                xml = await client.get_text(url, retries=1)
            except SourceUnavailable:
                continue
            events.extend(parse_atom_feed(xml, "youtube", channel_id, ctx))
            if len(events) >= ctx.limit:
                break
        if not events:
            raise SourceUnavailable("no channel RSS entries parsed")
        return events[: ctx.limit]


class DataApiStrategy(Strategy):
    """Official YouTube Data API v3 — activates when an API key is configured."""

    name = "data_api_v3"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        key = settings.youtube_api_key
        if not key:
            raise SourceUnavailable(
                "no YOUTUBE_API_KEY; Data API v3 answers 403 without one. "
                "The public trending feed strategy already covers this source."
            )

        events: list[RawEvent] = []
        query = " ".join(ctx.keywords) if ctx.keywords else "trending"
        for geo in (ctx.countries or ["US"])[:3]:
            url = (
                "https://www.googleapis.com/youtube/v3/search"
                f"?part=snippet&type=video&order=viewCount&maxResults=25"
                f"&q={query.replace(' ', '%20')}&regionCode={geo}&key={key}"
            )
            data = await client.get_json(url)
            for rank, item in enumerate(data.get("items") or [], start=1):
                snippet = item.get("snippet") or {}
                stats = item.get("statistics") or {}
                video_id = (item.get("id") or {}).get("videoId")
                if not video_id:
                    continue
                events.append(
                    RawEvent(
                        source_id="youtube",
                        external_id=f"yt:{video_id}",
                        title=snippet.get("title", ""),
                        url=f"https://www.youtube.com/watch?v={video_id}",
                        description=(snippet.get("description") or "")[:400],
                        activity=float(stats.get("viewCount") or 0),
                        activity_metric="views",
                        country_code=geo,
                        rank=rank,
                        category="video",
                        hashtags=snippet.get("tags") or [],
                        thumbnail=(snippet.get("thumbnails") or {})
                        .get("high", {})
                        .get("url"),
                        published_at=_parse_iso(snippet.get("publishedAt")),
                        metadata={
                            "channel": snippet.get("channelTitle"),
                            "geo": geo,
                            "strategy": "data_api_v3",
                            "like_count": stats.get("likeCount"),
                            "comment_count": stats.get("commentCount"),
                        },
                    )
                )
            if events:
                break
        if not events:
            raise SourceUnavailable("Data API returned no items")
        return events[: ctx.limit]


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@register_source
class YouTubeAdapter(SourceAdapter):
    source_id = "youtube"
    name = "YouTube"
    type = SourceType.SOCIAL
    description = (
        "Trending videos and Shorts per region from the public trending feed, "
        "plus new uploads from tracked channels. Upgrades to the official Data "
        "API automatically when a key is configured."
    )
    capabilities = [
        "videos",
        "shorts",
        "trending",
        "creators",
        "views",
        "country_geo",
        "recency",
    ]
    priority = 2
    collect_interval_seconds = 1200
    strategies = [SearchResultsStrategy(), ChannelRssStrategy(), DataApiStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)