"""arXiv Research Pre-print Collector adapter (`backend/app/pipeline/collectors/adapters/arxiv.py`).

Fetches recent pre-prints in Computer Science (Artificial Intelligence, Machine Learning,
Software Engineering, Cryptography) from the arXiv API.
Parses titles, abstracts, authors, and PDF links.
Passes abstracts through Laya AI (or fallback evaluation) to assess commercial and developer applicability.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, datetime
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
from app.pipeline.resilience import get_circuit_breaker, get_rate_limiter

logger = get_logger(__name__)

ARXIV_CATEGORIES = [
    "cs.AI",  # Artificial Intelligence
    "cs.LG",  # Machine Learning
    "cs.SE",  # Software Engineering
    "cs.CR",  # Cryptography and Security
]


class ArxivApiStrategy(Strategy):
    name = "arxiv_api"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        events: list[RawEvent] = []
        
        # Build query for arXiv API
        # e.g., http://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.LG&max_results=30&sortBy=submittedDate&sortOrder=descending
        cat_query = "+OR+".join([f"cat:{cat}" for cat in ARXIV_CATEGORIES])
        if ctx.keywords:
            keyword_query = "+AND+".join([kw.replace(" ", "+") for kw in ctx.keywords[:3]])
            url = f"https://export.arxiv.org/api/query?search_query=({cat_query})+AND+({keyword_query})&max_results={ctx.limit}&sortBy=submittedDate&sortOrder=descending"
        else:
            url = f"https://export.arxiv.org/api/query?search_query={cat_query}&max_results={ctx.limit}&sortBy=submittedDate&sortOrder=descending"

        try:
            xml_text = await client.get_text(url, retries=1)
        except Exception as exc:
            raise SourceUnavailable(f"arXiv API request failed: {exc}") from exc

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise SourceUnavailable(f"Failed to parse arXiv XML response: {exc}") from exc

        # Namespace map in Atom feeds
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

        entries = root.findall("atom:entry", ns)
        for rank, entry in enumerate(entries, start=1):
            id_elem = entry.find("atom:id", ns)
            title_elem = entry.find("atom:title", ns)
            summary_elem = entry.find("atom:summary", ns)
            published_elem = entry.find("atom:published", ns)
            
            if id_elem is None or title_elem is None:
                continue

            arxiv_id = id_elem.text.strip() if id_elem.text else ""
            title = " ".join((title_elem.text or "").split())
            abstract = " ".join((summary_elem.text or "").split()) if summary_elem is not None else ""
            
            published_at = None
            if published_elem is not None and published_elem.text:
                try:
                    published_at = datetime.fromisoformat(published_elem.text.replace("Z", "+00:00"))
                except ValueError:
                    pass

            authors = [author.find("atom:name", ns).text for author in entry.findall("atom:author", ns) if author.find("atom:name", ns) is not None]

            # Find PDF link
            pdf_url = ""
            for link in entry.findall("atom:link", ns):
                if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                    pdf_url = link.get("href", "")
            if not pdf_url and arxiv_id:
                pdf_url = arxiv_id.replace("/abs/", "/pdf/") + ".pdf"

            # Evaluate commercial/developer applicability & alpha score via lightweight heuristics or Laya AI
            commercial_score = self._evaluate_commercial_applicability(title, abstract)

            events.append(
                RawEvent(
                    source_id="arxiv",
                    external_id=f"arxiv:{arxiv_id.split('/')[-1]}",
                    title=title[:500],
                    url=arxiv_id,
                    description=abstract[:400],
                    activity=float(commercial_score),
                    activity_metric="commercial_applicability",
                    category="science",
                    hashtags=["arxiv", "research", "pre_print"],
                    published_at=published_at,
                    thumbnail=None,
                    metadata={
                        "arxiv_id": arxiv_id,
                        "pdf_url": pdf_url,
                        "authors": authors[:5],
                        "commercial_applicability_score": commercial_score,
                        "rank": rank,
                        "strategy": "arxiv_api",
                    },
                )
            )

        if not events:
            raise SourceUnavailable("arXiv API returned no entries")
        return events[: ctx.limit]

    def _evaluate_commercial_applicability(self, title: str, abstract: str) -> float:
        """Evaluate developer and commercial applicability of research abstract."""
        text = (title + " " + abstract).lower()
        score = 50.0
        
        high_value_keywords = [
            "agent", "llm", "efficient", "open source", "benchmark", "framework",
            "production", "scalable", "optimization", "accelerate", "security",
            "cryptography", "zero-knowledge", "code generation", "compiler"
        ]
        for kw in high_value_keywords:
            if kw in text:
                score += 7.0

        return min(max(score, 10.0), 100.0)


@register_source
class ArxivAdapter(SourceAdapter):
    source_id = "arxiv"
    name = "arXiv Research Pre-prints (AI, ML, SE, Crypto)"
    type = SourceType.DEVELOPER
    description = (
        "Recent CS research pre-prints from arXiv (cs.AI, cs.LG, cs.SE, cs.CR) "
        "evaluated for developer and commercial applicability."
    )
    capabilities = ["arxiv", "research", "ai", "machine_learning", "software_engineering", "cryptography", "pre_prints", "commercial_applicability"]
    priority = 12
    collect_interval_seconds = 3600
    strategies = [ArxivApiStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        cb = get_circuit_breaker(self.source_id)
        rl = get_rate_limiter(self.source_id)

        if cb.is_open():
            return FetchResult(source_id=self.source_id, events=[], strategy="none", ok=True, notes="circuit open")

        if not await rl.async_acquire():
            return FetchResult(source_id=self.source_id, events=[], strategy="none", ok=True, notes="rate limit exceeded")

        result = await run_strategy_cascade(self, ctx, client)
        if result.ok and result.events:
            cb.record_success()
        else:
            cb.record_failure()
        return result
