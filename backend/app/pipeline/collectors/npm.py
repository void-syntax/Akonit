"""npm registry search - new fast-growing developer packages with real downloads."""

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


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


class NpmSearchStrategy(Strategy):
    name = "registry_search"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        terms = ctx.keywords[:4] if ctx.keywords else ["ai", "agent", "openai"]
        events: list[RawEvent] = []
        for term in terms:
            url = (
                "https://registry.npmjs.org/-/v1/search"
                f"?text={term}&size=25&quality=popularity"
            )
            try:
                data = await client.get_json(url)
            except SourceUnavailable as exc:
                logger.debug("npm search %r failed: %s", term, exc)
                continue

            for rank, entry in enumerate(data.get("objects") or [], start=1):
                pkg = entry.get("package") or {}
                name = pkg.get("name")
                if not name:
                    continue
                title = name.strip()
                title_words = title.split()
                description = (pkg.get("description") or "").strip()
                desc_words = description.split()

                # Remove thin, uninformative items (1-2 word titles without context, code snippets, noise)
                if len(title_words) < 2 and len(description) < 30:
                    continue
                if len(desc_words) < 5 or description.lower() in ("a", "test", "package", "module", "npm package", "none", "todo", "foo", "bar", "null", "undefined"):
                    continue

                combined = f"{title} {description}".lower()
                code_indicators = ["import ", "const ", "function(", "def ", "class ", "console.log", "=>", "<?php", "select * from"]
                if any(ind in combined for ind in code_indicators) and len(description) < 30:
                    continue

                downloads = float((entry.get("downloads") or {}).get("monthly") or 0)
                weekly_downloads = float((entry.get("downloads") or {}).get("weekly") or (downloads / 4.0))
                if downloads < 100:
                    continue
                
                # Activity metric emphasizing weekly spike velocity
                activity_score = downloads + (weekly_downloads * 4.0)
                
                events.append(
                    RawEvent(
                        source_id="npm",
                        external_id=f"npm:{name}",
                        title=name,
                        url=pkg.get("links", {}).get("npm")
                        or f"https://www.npmjs.com/package/{name}",
                        description=(pkg.get("description") or "")[:400],
                        activity=activity_score,
                        activity_metric="download_velocity",
                        category="package",
                        hashtags=pkg.get("keywords") or [],
                        published_at=_parse_iso(pkg.get("date")),
                        metadata={
                            "monthly_downloads": downloads,
                            "weekly_downloads": weekly_downloads,
                            "download_velocity": round(weekly_downloads * 4.0, 2),
                            "dependents": entry.get("dependents"),
                            "search_score": entry.get("searchScore"),
                            "version": pkg.get("version"),
                            "rank": rank,
                            "strategy": "registry_search",
                        },
                    )
                )
            if events:
                break

        if not events:
            raise SourceUnavailable("npm search returned no packages")
        return events[: ctx.limit]


@register_source
class NpmAdapter(SourceAdapter):
    source_id = "npm"
    name = "npm"
    type = SourceType.DEVELOPER
    description = (
        "New and fast-growing developer packages with real monthly download "
        "counts from the public registry search."
    )
    capabilities = ["new_software", "dev_tools", "ai_packages", "downloads"]
    priority = 27
    collect_interval_seconds = 3600
    strategies = [NpmSearchStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)