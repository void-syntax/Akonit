"""Broad, near-real-time global news coverage from the GDELT DOC API."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
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
from app.pipeline.collectors.registry import register_source

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GLOBAL_QUERY = (
    "(technology OR startup OR science OR business OR finance OR health OR "
    "climate OR energy OR cybersecurity OR conflict OR election OR product OR AI)"
)


def _published_at(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for pattern in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


class GdeltRecentNewsStrategy(Strategy):
    name = "gdelt_doc_recent_articles"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        # Use a one-hour window: the service has rejected shorter windows in
        # live responses and this slow cadence also respects the shared quota.
        params = {
            "query": GLOBAL_QUERY,
            "mode": "artlist",
            "format": "json",
            "timespan": "1h",
            "sort": "datedesc",
            "maxrecords": min(max(ctx.limit, 1), 50),
        }
        # This public endpoint is rate limiting this installation. Don't spend
        # an extra retry sleep in the hot collection pass; the source's own
        # hourly schedule provides a natural retry window.
        payload = await client.get_json(GDELT_DOC_URL, params=params, retries=0)
        articles = payload.get("articles", []) if isinstance(payload, dict) else []
        events: list[RawEvent] = []
        seen_urls: set[str] = set()
        for item in articles:
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            domain = str(item.get("domain") or "").strip().lower()
            if not title or not url or url in seen_urls:
                continue
            seen_urls.add(url)
            digest = sha256(url.encode("utf-8", errors="ignore")).hexdigest()[:24]
            events.append(
                RawEvent(
                    source_id="gdelt_news",
                    external_id=f"gdelt:{digest}",
                    title=title[:500],
                    url=url,
                    description="",
                    activity=0.0,
                    activity_metric="news_mentions",
                    category="world_news",
                    published_at=_published_at(item.get("seendate")),
                    metadata={
                        "domain": domain,
                        "language": item.get("language"),
                        "source_country": item.get("sourcecountry"),
                        "source_collection": item.get("sourceCollection"),
                        "strategy": self.name,
                    },
                )
            )
            if len(events) >= ctx.limit:
                break
        if not events:
            raise SourceUnavailable("GDELT returned no recent articles")
        return events


@register_source
class GdeltNewsAdapter(SourceAdapter):
    source_id = "gdelt_news"
    name = "GDELT Global News"
    type = SourceType.NEWS
    description = (
        "Broad global news search across multilingual coverage, updated on a "
        "15-minute window. Public API; no credentials required."
    )
    capabilities = ["global_news", "multilingual", "breaking_news", "cross_source"]
    priority = 5
    # GDELT's public endpoint has returned 429s here. Keep requests to one per
    # hour and let the other world-news feeds provide minute-level coverage.
    collect_interval_seconds = 3600
    strategies = [GdeltRecentNewsStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        from app.pipeline.collectors.registry import run_strategy_cascade

        return await run_strategy_cascade(self, ctx, client)
