"""Hacker News - new tech topics with discussion velocity.

Two complementary strategies:
  1. firebase_top   - Top stories via public Firebase API (no auth, always free).
  2. algolia_recent - Stories from the last 24h sorted by points via the free
                      Algolia HN Search API (no key required).
                      Endpoint: https://hn.algolia.com/api/v1/search_by_date
                      Filters:  tags=story, numericFilters=created_at_i>{unix},points>10
                      This catches stories that spike fast but haven't made the
                      "top" list yet — ideal for early signal detection.
"""

from __future__ import annotations

import asyncio
import time
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


class HackerNewsFirebaseStrategy(Strategy):
    name = "firebase_top"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        ids = await client.get_json(
            "https://hacker-news.firebaseio.com/v0/topstories.json"
        )
        if not isinstance(ids, list):
            raise SourceUnavailable("unexpected HN payload")

        story_ids = ids[: min(max(ctx.limit, 1), 20)]
        items = await asyncio.gather(
            *(
                client.get_json(
                    f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
                    retries=1,
                )
                for story_id in story_ids
            ),
            return_exceptions=True,
        )

        events: list[RawEvent] = []
        for story_id, item in zip(story_ids, items, strict=True):
            if isinstance(item, BaseException):
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


class HackerNewsAlgoliaStrategy(Strategy):
    """HN stories from the last 24h sorted by points — free Algolia endpoint, no key.

    URL: https://hn.algolia.com/api/v1/search_by_date
    This endpoint returns stories chronologically but we ask for those with the
    most points in the last day, giving us fast-rising items before they reach
    the Firebase topstories list.
    """

    name = "algolia_recent"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        since = int(time.time()) - 86_400  # last 24 hours
        url = (
            "https://hn.algolia.com/api/v1/search_by_date"
            f"?tags=story&numericFilters=created_at_i>{since},points>5"
            "&hitsPerPage=30"
        )
        try:
            data = await client.get_json(url, retries=1)
        except Exception as exc:
            raise SourceUnavailable(f"algolia HN request failed: {exc}") from exc

        hits = data.get("hits") if isinstance(data, dict) else None
        if not hits:
            raise SourceUnavailable("algolia HN returned no hits")

        # Sort locally by points descending — the endpoint sorts by date
        hits = sorted(hits, key=lambda h: h.get("points") or 0, reverse=True)

        events: list[RawEvent] = []
        for hit in hits[: ctx.limit]:
            story_id = hit.get("objectID") or hit.get("story_id")
            title = hit.get("title")
            if not title or not story_id:
                continue
            url_val = hit.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
            score = float(hit.get("points") or 0)
            comments = float(hit.get("num_comments") or 0)
            created_at = hit.get("created_at_i")
            published = (
                datetime.fromtimestamp(float(created_at), tz=UTC) if created_at else None
            )
            events.append(
                RawEvent(
                    source_id="hackernews",
                    external_id=f"hn:{story_id}",
                    title=title[:500],
                    url=url_val,
                    description=(hit.get("story_text") or "")[:400],
                    activity=score + comments * 2.5,
                    activity_metric="discussion_velocity",
                    category="tech_discussion",
                    published_at=published,
                    metadata={
                        "score": score,
                        "comments": comments,
                        "by": hit.get("author"),
                        "hn_url": f"https://news.ycombinator.com/item?id={story_id}",
                        "strategy": "algolia_recent",
                    },
                )
            )

        if not events:
            raise SourceUnavailable("algolia HN: no valid stories after filtering")
        return events


@register_source
class HackerNewsAdapter(SourceAdapter):
    source_id = "hackernews"
    name = "Hacker News"
    type = SourceType.COMMUNITY
    description = (
        "New tech topics, tools and startups with discussion velocity. "
        "Uses Firebase top stories + Algolia 24h trending for early signal detection."
    )
    capabilities = ["ai", "startups", "tools", "discussions", "velocity"]
    priority = 26
    collect_interval_seconds = 1800
    strategies = [HackerNewsFirebaseStrategy(), HackerNewsAlgoliaStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)
