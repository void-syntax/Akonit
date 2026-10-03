"""Stack Overflow - new developer questions revealing emerging tools."""

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


class StackExchangeStrategy(Strategy):
    name = "api_2_3"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        data = await client.get_json(
            "https://api.stackexchange.com/2.3/questions"
            "?order=desc&sort=creation&site=stackoverflow&pagesize=40"
        )
        events: list[RawEvent] = []
        for rank, item in enumerate(data.get("items") or [], start=1):
            title = item.get("title")
            if not title:
                continue
            score = float(item.get("score") or 0)
            answers = float(item.get("answer_count") or 0)
            events.append(
                RawEvent(
                    source_id="stackoverflow",
                    external_id=f"so:{item.get('question_id')}",
                    title=title[:500],
                    url=item.get("link") or "",
                    description=(item.get("title") or "")[:400],
                    activity=score + answers,
                    activity_metric="score_plus_answers",
                    category="question",
                    hashtags=item.get("tags") or [],
                    published_at=datetime.fromtimestamp(
                        item.get("creation_date", 0), tz=UTC
                    ),
                    metadata={
                        "score": score,
                        "answers": answers,
                        "views": item.get("view_count"),
                        "rank": rank,
                        "strategy": "api_2_3",
                    },
                )
            )
        if not events:
            raise SourceUnavailable("stackexchange returned no questions")
        return events[: ctx.limit]


@register_source
class StackOverflowAdapter(SourceAdapter):
    source_id = "stackoverflow"
    name = "Stack Overflow"
    type = SourceType.COMMUNITY
    description = "New developer questions revealing emerging tools and pain points."
    capabilities = ["developer", "tools", "problems", "new_software"]
    priority = 30
    collect_interval_seconds = 5400
    strategies = [StackExchangeStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)