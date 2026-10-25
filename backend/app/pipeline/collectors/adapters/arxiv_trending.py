"""arXiv AI/ML Trending Pre-prints Collector adapter (`backend/app/pipeline/collectors/adapters/arxiv_trending.py`).

Fetches cutting-edge AI and ML pre-prints from arXiv API (`https://export.arxiv.org/api/query`)
sorted by submission date, extracts citation velocity indicators and author metadata.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
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


class ArxivTrendingStrategy(Strategy):
    name = "arxiv_trending_api"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        url = (
            "https://export.arxiv.org/api/query"
            "?search_query=cat:cs.AI+OR+cat:cs.LG+OR+cat:stat.ML"
            f"&max_results={max(ctx.limit, 30)}"
            "&sortBy=submittedDate&sortOrder=descending"
        )
        try:
            xml_text = await client.get_text(url, retries=1)
        except Exception as exc:
            raise SourceUnavailable(f"arXiv API request failed: {exc}") from exc

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise SourceUnavailable(f"Failed to parse arXiv XML: {exc}") from exc

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)

        events: list[RawEvent] = []
        for rank, entry in enumerate(entries, start=1):
            id_elem = entry.find("atom:id", ns)
            title_elem = entry.find("atom:title", ns)
            summary_elem = entry.find("atom:summary", ns)
            published_elem = entry.find("atom:published", ns)

            if id_elem is None or title_elem is None:
                continue

            arxiv_url = (id_elem.text or "").strip()
            title = " ".join((title_elem.text or "").split())
            abstract = " ".join((summary_elem.text or "").split()) if summary_elem is not None else ""
            paper_id = arxiv_url.split("/")[-1]

            published_at = None
            if published_elem is not None and published_elem.text:
                try:
                    published_at = datetime.fromisoformat(
                        published_elem.text.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            authors = [
                author.find("atom:name", ns).text
                for author in entry.findall("atom:author", ns)
                if author.find("atom:name", ns) is not None
            ]

            # Activity metric: recency + author count / categories as proxy
            activity = float(len(authors) * 10.0 + (30 - rank))

            events.append(
                RawEvent(
                    source_id="arxiv_trending",
                    external_id=f"arxiv:{paper_id}",
                    title=title[:500],
                    url=arxiv_url,
                    description=abstract[:400],
                    activity=activity,
                    activity_metric="paper_velocity",
                    rank=rank,
                    category="research_paper",
                    hashtags=["ai", "machine_learning", "pre_print"],
                    published_at=published_at,
                    metadata={
                        "paper_id": paper_id,
                        "authors": authors[:5],
                        "primary_category": "cs.AI",
                        "strategy": "arxiv_trending_api",
                    },
                )
            )

        if not events:
            raise SourceUnavailable("arXiv trending returned no papers")
        return events[: ctx.limit]


@register_source
class ArxivTrendingAdapter(SourceAdapter):
    source_id = "arxiv_trending"
    name = "arXiv AI Pre-prints"
    type = SourceType.RESEARCH if hasattr(SourceType, "RESEARCH") else SourceType.NEWS
    description = (
        "Cutting-edge AI and Machine Learning pre-prints from arXiv. "
        "Tracks foundational research before commercial adoption."
    )
    capabilities = ["ai_research", "pre_prints", "models", "algorithms", "science"]
    priority = 18
    cost = 0.0
    credentials_required = False
    collect_interval_seconds = 7200
    strategies = [ArxivTrendingStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)
