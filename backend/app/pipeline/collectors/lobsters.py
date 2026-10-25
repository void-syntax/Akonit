"""Lobsters — нативный JSON API (без ключа, без авторизации).

Исследование показало, что Lobsters natively возвращает JSON на всех основных страницах
при добавлении суффикса `.json`:
- https://lobste.rs/hottest.json
- https://lobste.rs/recent.json

Это дает реальные очки (score), число комментариев, теги и автора вместо
ограниченного RSS-канала.
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


class LobstersJsonStrategy(Strategy):
    """Fetch hottest and recent stories via Lobsters native JSON endpoints."""

    name = "native_json"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        events: list[RawEvent] = []
        seen: set[str] = set()

        for endpoint in ("hottest", "recent"):
            url = f"https://lobste.rs/{endpoint}.json"
            try:
                data = await client.get_json(url, retries=1)
            except Exception as exc:
                logger.debug("lobsters %s.json failed: %s", endpoint, exc)
                continue

            if not isinstance(data, list):
                continue

            for rank, item in enumerate(data, start=1):
                short_id = item.get("short_id")
                if not short_id or short_id in seen:
                    continue
                seen.add(short_id)

                title = item.get("title")
                url_val = item.get("url") or item.get("comments_url")
                if not title or not url_val:
                    continue

                score = float(item.get("score") or 0)
                comments = float(item.get("comment_count") or 0)
                activity = score + (comments * 2.0)

                created_at = item.get("created_at")
                try:
                    published = (
                        datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        if created_at
                        else None
                    )
                except ValueError:
                    published = None

                tags = item.get("tags") or []
                submitter = (item.get("submitter_user") or {}).get("username")

                events.append(
                    RawEvent(
                        source_id="lobsters",
                        external_id=f"lob:{short_id}",
                        title=title[:500],
                        url=url_val,
                        description=(item.get("description") or "")[:400],
                        activity=activity,
                        activity_metric="score_plus_comments",
                        rank=rank if endpoint == "hottest" else None,
                        category="tech_discussion",
                        hashtags=tags,
                        published_at=published,
                        metadata={
                            "score": score,
                            "comments": comments,
                            "submitter": submitter,
                            "endpoint": endpoint,
                            "strategy": "native_json",
                        },
                    )
                )

            if len(events) >= ctx.limit:
                break

        if not events:
            raise SourceUnavailable("lobsters native JSON returned no items")

        events.sort(key=lambda e: e.activity, reverse=True)
        return events[: ctx.limit]


@register_source
class LobstersAdapter(SourceAdapter):
    source_id = "lobsters"
    name = "Lobsters"
    type = SourceType.COMMUNITY
    description = (
        "New developer tools, side projects and tech releases from Lobsters. "
        "Uses the native JSON API (`hottest.json` / `recent.json`) for precise "
        "scores, comment counts, and metadata."
    )
    capabilities = ["dev_tools", "side_projects", "tech", "new_software", "velocity"]
    priority = 29
    cost = 0.0
    credentials_required = False
    collect_interval_seconds = 3600
    strategies = [LobstersJsonStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)
