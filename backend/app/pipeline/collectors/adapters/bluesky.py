"""Bluesky AT Protocol Real-Time Firehose Collector adapter (`backend/app/pipeline/collectors/adapters/bluesky.py`).
Connects to Bluesky public feed / AT Protocol repository stream or public search endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime
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


class BlueskyPublicFeedStrategy(Strategy):
    name = "bluesky_public_feed"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        events: list[RawEvent] = []
        # Use public Bluesky appview / X-Repo feed or public search endpoint
        url = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
        
        query_terms = " ".join(ctx.keywords) if ctx.keywords else "tech AI startup"
        headers = {"User-Agent": "AkonitSignalRadar/1.0 (OSINT)"}

        try:
            data = await client.get_json(
                url,
                params={"q": query_terms, "limit": min(max(ctx.limit, 1), 25)},
                headers=headers,
                retries=1,
            )
        except Exception as exc:
            raise SourceUnavailable(f"Bluesky API request failed: {exc}") from exc

        posts = data.get("posts", []) if isinstance(data, dict) else []
        for post in posts:
            record = post.get("record", {})
            text = record.get("text", "")
            author = post.get("author", {})
            handle = author.get("handle", "unknown")
            uri = post.get("uri", "")
            created_at_str = record.get("createdAt")
            
            try:
                observed_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00")) if created_at_str else datetime.now(UTC)
            except Exception:
                observed_at = datetime.now(UTC)

            events.append(
                RawEvent(
                    source_id="bluesky",
                    external_id=uri or f"bsky-{handle}-{datetime.now(UTC).timestamp()}",
                    title=f"Bluesky post by @{handle}",
                    content=text,
                    url=f"https://bsky.app/profile/{handle}",
                    observed_at=observed_at,
                    author=handle,
                    metrics={"likes": post.get("likeCount", 0), "reposts": post.get("repostCount", 0)},
                )
            )

        return events


@register_source
class BlueskyAdapter(SourceAdapter):
    source_id = "bluesky"
    name = "Bluesky AT Feed"
    type = SourceType.SOCIAL
    adapter_name = "bluesky"
    description = "Decentralized real-time social posts from Bluesky AT Protocol public feeds."
    priority = 2
    cost = 0.0
    credentials_required = False
    collect_interval_seconds = 120
    capabilities = ["social", "realtime", "microblogging"]
    strategies = [BlueskyPublicFeedStrategy()]
