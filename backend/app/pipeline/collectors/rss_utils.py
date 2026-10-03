"""Shared Atom/RSS parsing used by several adapters."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.pipeline.collectors.base import FetchContext, RawEvent

FEED_RE = re.compile(r"<item>(.*?)</item>", re.S)
ATOM_RE = re.compile(r"<entry>(.*?)</entry>", re.S)
FIELD_PATTERNS = {
    "title": [re.compile(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", re.S)],
    "link": [
        re.compile(r"<link[^>]*href=\"(.*?)\"", re.S),
        re.compile(r"<link>(.*?)</link>", re.S),
    ],
    "description": [
        re.compile(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", re.S)
    ],
    "content": [
        re.compile(r"<content[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</content>", re.S)
    ],
    "published": [
        re.compile(r"<published>(.*?)</published>", re.S),
        re.compile(r"<pubDate>(.*?)</pubDate>", re.S),
        re.compile(r"<updated>(.*?)</updated>", re.S),
    ],
}
TAG_RE = re.compile(r"<(?:category|media:tag)[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</", re.S)


def _clean(text: str) -> str:
    text = (
        text.replace("<![CDATA[", "")
        .replace("]]>", "")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def _field(block: str, name: str) -> str | None:
    for pattern in FIELD_PATTERNS[name]:
        m = pattern.search(block)
        if m:
            return _clean(m.group(1))
    return None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    from email.utils import parsedate_to_datetime

    for parser in (parsedate_to_datetime, _iso):
        try:
            dt = parser(value)
            if dt:
                return dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            continue
    return None


def _iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


def parse_feed(xml: str) -> list[dict[str, Any]]:
    """Return raw-ish dicts for every item/entry in an RSS or Atom document."""
    blocks = FEED_RE.findall(xml) or ATOM_RE.findall(xml)
    out: list[dict[str, Any]] = []
    for block in blocks:
        out.append(
            {
                "title": _field(block, "title"),
                "link": _field(block, "link"),
                "description": _field(block, "description") or _field(block, "content"),
                "published": _parse_date(_field(block, "published")),
                "tags": [_clean(t) for t in TAG_RE.findall(block)],
            }
        )
    return out


def parse_atom_feed(
    xml: str,
    source_id: str,
    channel_id: str,
    ctx: FetchContext,
) -> list[RawEvent]:
    events: list[RawEvent] = []
    country = ctx.countries[0] if ctx.countries else None
    for item in parse_feed(xml):
        if not item["title"] or not item["link"]:
            continue
        events.append(
            RawEvent(
                source_id=source_id,
                external_id=f"{source_id}:{item['link'].rsplit('=', 1)[-1][:11]}",
                title=item["title"],
                url=item["link"],
                description=(item["description"] or "")[:400],
                activity=0.0,
                activity_metric="views",
                country_code=country,
                category="video",
                hashtags=item["tags"],
                published_at=item["published"],
                thumbnail=None,
                metadata={"channel_id": channel_id, "strategy": "channel_rss"},
            )
        )
    return events