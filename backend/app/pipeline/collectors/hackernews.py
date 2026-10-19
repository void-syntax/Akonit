"""Hacker News - new tech topics with discussion velocity. Public Firebase API."""

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


class HackerNewsStrategy(Strategy):
    name = "firebase_top"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        ids = await client.get_json(
            "https://hacker-news.firebaseio.com/v0/topstories.json"
        )
        if not isinstance(ids, list):
            raise SourceUnavailable("unexpected HN payload")

        events: list[RawEvent] = []
        for story_id in ids[:60]:
            try:
                item = await client.get_json(
                    f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
                    retries=1,
                )
            except SourceUnavailable:
                continue
            if not item or item.get("type") != "story":
                continue
            url = item.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
            score = float(item.get("score") or 0)
            comments = float(item.get("descendants") or 0)
            discussion_heat = score + (comments * 2.5)
            events.append(
                RawEvent(
                    source_id="hackernews",
                    external_id=f"hn:{story_id}",
                    title=item.get("title", "")[:500],
                    url=url,
                    description=(item.get("text") or "")[:400],
                    activity=discussion_heat,
                    activity_metric="discussion_velocity",
                    category="tech_discussion",
                    published_at=datetime.fromtimestamp(
                        item.get("time", 0), tz=UTC
                    ),
                    metadata={
                        "score": score,
                        "comments": comments,
                        "discussion_heat": discussion_heat,
                        "by": item.get("by"),
                        "hn_url": f"https://news.ycombinator.com/item?id={story_id}",
                        "strategy": "firebase_top",
                    },
                )
            )
            if len(events) >= ctx.limit:
                break

        if not events:
            raise SourceUnavailable("no HN stories parsed")
        return events[: ctx.limit]


@register_source
class HackerNewsAdapter(SourceAdapter):
    source_id = "hackernews"
    name = "Hacker News"
    type = SourceType.COMMUNITY
    description = (
        "New tech topics, tools and startups with discussion velocity from "
        "the public Firebase API."
    )
    capabilities = ["ai", "startups", "tools", "discussions", "velocity"]
    priority = 26
    collect_interval_seconds = 1800
    strategies = [HackerNewsStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)