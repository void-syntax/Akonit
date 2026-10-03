"""DEV Community - fast-rising technical articles with reaction velocity."""

from __future__ import annotations

from datetime import UTC, datetime
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


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


class DevToStrategy(Strategy):
    name = "articles_api"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        items = await client.get_json(
            "https://dev.to/api/articles?per_page=30&top=7"
        )
        events: list[RawEvent] = []
        for rank, item in enumerate(items or [], start=1):
            title = item.get("title")
            if not title:
                continue
            reactions = float(item.get("positive_reactions_count") or 0)
            comments = float(item.get("comments_count") or 0)
            events.append(
                RawEvent(
                    source_id="devto",
                    external_id=f"dev:{item.get('id')}",
                    title=title[:500],
                    url=item.get("url") or "",
                    description=(item.get("description") or "")[:400],
                    activity=reactions + comments * 2,
                    activity_metric="reactions",
                    category="article",
                    hashtags=[
                        t.get("name", "")
                        if isinstance(t, dict)
                        else str(t)
                        for t in (item.get("tag_list") or [])
                    ],
                    published_at=_parse_iso(item.get("published_at")),
                    thumbnail=item.get("cover_image")
                    or item.get("profile_image"),
                    metadata={
                        "reactions": reactions,
                        "comments": comments,
                        "reading_minutes": item.get("reading_time_minutes"),
                        "author": item.get("user", {}).get("name"),
                        "rank": rank,
                        "strategy": "articles_api",
                    },
                )
            )
        if not events:
            raise SourceUnavailable("dev.to returned no articles")
        return events[: ctx.limit]


@register_source
class DevToAdapter(SourceAdapter):
    source_id = "devto"
    name = "DEV Community"
    type = SourceType.COMMUNITY
    description = "Fast-rising technical articles with reaction velocity."
    capabilities = ["dev_content", "ai", "tutorials", "reactions"]
    priority = 28
    collect_interval_seconds = 3600
    strategies = [DevToStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)