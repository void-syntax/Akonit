"""Priority #3 — AI / tech / new product sources.

All verified working without credentials:
  * GitHub search/repositories                 -> OK (60/h anon, 5000 with token)
  * Hugging Face /api/models|spaces|datasets    -> OK
  * Product Hunt /feed (RSS)                   -> OK
  * Hacker News firebase + hnrss.org/newest    -> OK
  * npm registry /-/v1/search                  -> OK
  * DEV /api/articles                          -> OK
  * Lobsters /rss                              -> OK
  * Stack Exchange 2.3 API                     -> OK
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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

logger = get_logger(__name__)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------- GitHub
class GitHubSearchStrategy(Strategy):
    name = "search_api"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        since = datetime.now(UTC) - timedelta(hours=48)
        queries = ctx.keywords[:4] if ctx.keywords else ["", "ai", "agent", "llm"]
        headers = {}
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"

        events: list[RawEvent] = []
        for topic in queries:
            q = f"created:>{since.strftime('%Y-%m-%dT%H:%M:%SZ')} stars:>20"
            if topic:
                q += f" {topic}"
            url = (
                "https://api.github.com/search/repositories"
                f"?q={q.replace(' ', '+')}&sort=stars&order=desc&per_page=30"
            )
            try:
                data = await client.get_json(url, headers=headers)
            except SourceUnavailable as exc:
                logger.debug("github search %r failed: %s", topic, exc)
                continue

            for rank, item in enumerate(data.get("items") or [], start=1):
                stars = float(item.get("stargazers_count") or 0)
                forks = float(item.get("forks_count") or 0)
                events.append(
                    RawEvent(
                        source_id="github",
                        external_id=f"gh:{item['full_name']}",
                        title=item["full_name"],
                        url=item.get("html_url") or "",
                        description=(item.get("description") or "")[:400],
                        activity=stars + forks * 2,
                        activity_metric="stars",
                        category="repository",
                        hashtags=item.get("topics") or [],
                        published_at=parse_iso(item.get("created_at")),
                        thumbnail=item.get("owner", {}).get("avatar_url"),
                        metadata={
                            "stars": stars,
                            "forks": forks,
                            "watchers": item.get("watchers_count"),
                            "open_issues": item.get("open_issues_count"),
                            "language": item.get("language"),
                            "topics": item.get("topics") or [],
                            "rank": rank,
                            "license": (item.get("license") or {}).get("spdx_id"),
                            "strategy": "search_api",
                        },
                    )
                )
            if events:
                break

        if not events:
            raise SourceUnavailable("github search returned no repositories")
        return events[: ctx.limit]


@register_source
class GitHubAdapter(SourceAdapter):
    source_id = "github"
    name = "GitHub"
    type = SourceType.DEVELOPER
    description = (
        "New repositories with fast star velocity, not the popular ones. "
        "Anonymous access works; a token raises the limit from 60 to 5000/h."
    )
    capabilities = ["new_ai", "open_source", "dev_tools", "stars_velocity", "releases"]
    priority = 20
    collect_interval_seconds = 1800
    strategies = [GitHubSearchStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)


# --------------------------------------------------------- Hugging Face
class HuggingFaceTrendingStrategy(Strategy):
    name = "hub_api"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        headers = {}
        if settings.hf_token:
            headers["Authorization"] = f"Bearer {settings.hf_token}"

        events: list[RawEvent] = []
        for kind in ("models", "spaces", "datasets"):
            url = (
                f"https://huggingface.co/api/{kind}"
                "?sort=trendingScore&direction=-1&limit=25"
            )
            try:
                items = await client.get_json(url, headers=headers)
            except SourceUnavailable as exc:
                logger.debug("hf %s failed: %s", kind, exc)
                continue

            for rank, item in enumerate(items or [], start=1):
                model_id = item.get("id") or item.get("modelId")
                if not model_id:
                    continue
                likes = float(item.get("likes") or 0)
                downloads = float(item.get("downloads") or 0)
                events.append(
                    RawEvent(
                        source_id="huggingface",
                        external_id=f"hf:{kind}:{model_id}",
                        title=model_id,
                        url=f"https://huggingface.co/{kind}/{model_id}",
                        description=str(item.get("pipeline_tag") or "")[:200],
                        activity=likes + downloads / 1000,
                        activity_metric="likes",
                        category=kind,
                        hashtags=item.get("tags") or [],
                        published_at=parse_iso(item.get("createdAt")),
                        metadata={
                            "likes": likes,
                            "downloads": downloads,
                            "trending_score": item.get("trendingScore"),
                            "pipeline_tag": item.get("pipeline_tag"),
                            "kind": kind,
                            "rank": rank,
                            "last_modified": item.get("lastModified"),
                            "strategy": "hub_api",
                        },
                    )
                )
            if len(events) >= ctx.limit:
                break

        if not events:
            raise SourceUnavailable("huggingface hub api returned no items")
        return events[: ctx.limit]


@register_source
class HuggingFaceAdapter(SourceAdapter):
    source_id = "huggingface"
    name = "Hugging Face"
    type = SourceType.DEVELOPER
    description = (
        "Trending models, Spaces and datasets with likes, downloads and "
        "trending score. Open Hub API, no credentials required."
    )
    capabilities = ["new_ai", "free_ai", "open_source_ai", "models", "datasets"]
    priority = 21
    collect_interval_seconds = 1800
    strategies = [HuggingFaceTrendingStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)