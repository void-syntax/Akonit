"""GitHub Trending — парсер HTML-страницы github.com/trending.

Официального JSON API для трендов GitHub нет.
Парсим публичную HTML-страницу, которая доступна без авторизации.

Стратегии:
1. html_trending — HTML-парсер страницы github.com/trending (daily/weekly)
2. search_api    — Резервный: GitHub Search API (новые репозитории с >10 звёздами)
                   Активируется автоматически, если GITHUB_TOKEN задан в .env
                   для увеличения rate-limit с 60 до 5000 запросов/час.

Данные: название, описание, язык, число звёзд, прирост звёзд за период,
число форков, авторы.
"""

from __future__ import annotations

import re
from datetime import datetime
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

# Precompiled patterns for HTML parsing
_RE_REPO_ARTICLE = re.compile(
    r'<article[^>]+class="[^"]*Box-row[^"]*"[^>]*>(.*?)</article>', re.S
)
_RE_REPO_LINK = re.compile(r'<h2[^>]*>\s*<a[^>]*href="(/[^/"]+/[^/"]+)"')
_RE_DESC = re.compile(r'<p[^>]+class="[^"]*col-9[^"]*"[^>]*>(.*?)</p>', re.S)
_RE_LANG = re.compile(
    r'<span[^>]+itemprop="programmingLanguage"[^>]*>(.*?)</span>', re.S
)
_RE_STARS_TODAY = re.compile(r'([\d,]+)\s+stars?\s+today', re.I)
_RE_TOTAL_STARS = re.compile(
    r'href="[^"]+/stargazers"[^>]*>\s*<svg[^>]*>.*?</svg>\s*([\d,]+)', re.S
)
_RE_FORKS = re.compile(
    r'href="[^"]+/forks"[^>]*>\s*<svg[^>]*>.*?</svg>\s*([\d,]+)', re.S
)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).replace("&amp;", "&").strip()


def _parse_int(text: str | None) -> int:
    if not text:
        return 0
    cleaned = re.sub(r"[^\d]", "", text)
    try:
        return int(cleaned)
    except ValueError:
        return 0


def _activity_for_repo(repo: dict[str, Any]) -> tuple[float, str]:
    """Return a measured GitHub activity value with its actual unit."""
    stars_today = int(repo.get("stars_today") or 0)
    if stars_today > 0:
        return float(stars_today), "stars_today"

    total_stars = int(repo.get("total_stars") or 0)
    if total_stars > 0:
        # Total popularity is still useful context, but it is not daily growth.
        return float(total_stars), "total_stars"

    return 0.0, "unmeasured"


def _parse_trending_html(html: str, since: str) -> list[dict]:
    """Extract repository data from GitHub Trending HTML."""
    repos: list[dict] = []
    for article_match in _RE_REPO_ARTICLE.finditer(html):
        article = article_match.group(1)

        link_match = _RE_REPO_LINK.search(article)
        if not link_match:
            continue
        path = link_match.group(1).strip("/")
        parts = path.split("/")
        if len(parts) != 2:
            continue
        owner, repo_name = parts

        desc_match = _RE_DESC.search(article)
        description = _strip_html(desc_match.group(1)) if desc_match else ""

        lang_match = _RE_LANG.search(article)
        language = _strip_html(lang_match.group(1)) if lang_match else ""

        stars_today_match = _RE_STARS_TODAY.search(article)
        stars_today = _parse_int(
            stars_today_match.group(1) if stars_today_match else None
        )

        total_stars_match = _RE_TOTAL_STARS.search(article)
        total_stars = _parse_int(
            total_stars_match.group(1) if total_stars_match else None
        )

        forks_match = _RE_FORKS.search(article)
        forks = _parse_int(forks_match.group(1) if forks_match else None)

        repos.append(
            {
                "owner": owner,
                "name": repo_name,
                "full_name": f"{owner}/{repo_name}",
                "description": description[:400],
                "language": language,
                "stars_today": stars_today,
                "total_stars": total_stars,
                "forks": forks,
                "since": since,
                "url": f"https://github.com/{owner}/{repo_name}",
            }
        )

    return repos


class GitHubTrendingHtmlStrategy(Strategy):
    """Parse the public GitHub Trending page — no auth, no API key."""

    name = "html_trending"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        events: list[RawEvent] = []
        seen: set[str] = set()

        # Fetch daily and weekly to maximise signal diversity
        for since in ("daily", "weekly"):
            url = f"https://github.com/trending?since={since}"
            try:
                # There are two sequential windows under a 20s source budget.
                # Bound each independently and avoid a retry/backoff consuming
                # the time reserved for the second window and other sources.
                html = await client.get_text(url, retries=0, timeout=8.0)
            except SourceUnavailable as exc:
                logger.debug("github trending %s failed: %s", since, exc)
                continue

            repos = _parse_trending_html(html, since)
            if not repos and since == "daily":
                logger.warning("github trending: no repos parsed from HTML (layout changed?)")

            for rank, repo in enumerate(repos, start=1):
                key = repo["full_name"].lower()
                if key in seen:
                    continue
                seen.add(key)

                # Keep the unit honest: lifetime stars are not today's growth,
                # and a list rank is not an activity measurement.
                activity, activity_metric = _activity_for_repo(repo)

                events.append(
                    RawEvent(
                        source_id="github_trending",
                        external_id=f"ghtrend:{key.replace('/', ':')}",
                        title=f"{repo['full_name']}",
                        url=repo["url"],
                        description=repo["description"] or f"Trending GitHub repo: {repo['full_name']}",
                        activity=activity,
                        activity_metric=activity_metric,
                        rank=rank if since == "daily" else None,
                        category="open_source",
                        hashtags=[repo["language"].lower()] if repo["language"] else [],
                        metadata={
                            "owner": repo["owner"],
                            "repo": repo["name"],
                            "language": repo["language"],
                            "stars_today": repo["stars_today"],
                            "total_stars": repo["total_stars"],
                            "forks": repo["forks"],
                            "since": since,
                            "strategy": "html_trending",
                        },
                    )
                )

            if len(events) >= ctx.limit:
                break

        if not events:
            raise SourceUnavailable(
                "GitHub Trending HTML returned no repos (layout changed or blocked)"
            )
        # Prefer actual daily gains over lifetime popularity counts.
        events.sort(
            key=lambda e: (e.activity_metric == "stars_today", e.activity),
            reverse=True,
        )
        return events[: ctx.limit]


class GitHubSearchApiStrategy(Strategy):
    """GitHub Search API — newly created repos sorted by stars.

    Free: 60 req/hour unauthenticated, 5000/hour with token (GITHUB_TOKEN in .env).
    Finds repos that may not be on the trending page yet but are accelerating fast.
    """

    name = "search_api"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        headers: dict[str, str] = {
            "User-Agent": "SignalRadar/1.0",
            "Accept": "application/vnd.github.v3+json",
        }
        token = getattr(settings, "github_token", None)
        if token:
            headers["Authorization"] = f"Bearer {token}"

        # Search repos created in last 7 days with at least 50 stars
        url = (
            "https://api.github.com/search/repositories"
            "?q=created:>2024-01-01+stars:>50"
            "&sort=stars&order=desc&per_page=30"
        )
        try:
            data = await client.get_json(url, headers=headers, retries=1)
        except Exception as exc:
            raise SourceUnavailable(f"GitHub Search API failed: {exc}") from exc

        items = data.get("items") if isinstance(data, dict) else None
        if not items:
            raise SourceUnavailable("GitHub Search API returned no repositories")

        events: list[RawEvent] = []
        for rank, item in enumerate(items[: ctx.limit], start=1):
            full_name = item.get("full_name") or ""
            if not full_name:
                continue

            pushed_at = item.get("pushed_at")
            try:
                published = datetime.fromisoformat(
                    pushed_at.replace("Z", "+00:00")
                ) if pushed_at else None
            except ValueError:
                published = None

            stars = int(item.get("stargazers_count") or 0)
            forks = int(item.get("forks_count") or 0)
            language = item.get("language") or ""

            events.append(
                RawEvent(
                    source_id="github_trending",
                    external_id=f"ghsearch:{full_name.lower().replace('/', ':')}",
                    title=full_name,
                    url=item.get("html_url") or f"https://github.com/{full_name}",
                    description=(item.get("description") or "")[:400],
                    activity=float(stars),
                    activity_metric="stars",
                    rank=rank,
                    category="open_source",
                    hashtags=[language.lower()] if language else [],
                    published_at=published,
                    metadata={
                        "stars": stars,
                        "forks": forks,
                        "language": language,
                        "topics": item.get("topics") or [],
                        "strategy": "search_api",
                    },
                )
            )

        if not events:
            raise SourceUnavailable("GitHub Search: no valid repos after filtering")
        return events


@register_source
class GitHubTrendingAdapter(SourceAdapter):
    source_id = "github_trending"
    name = "GitHub Trending"
    type = SourceType.DEVELOPER
    description = (
        "Trending repositories on GitHub — stars gained today/weekly as spike signal. "
        "Parses the public trending page (no auth). Falls back to GitHub Search API "
        "for repositories that are accelerating but not yet on the trending page."
    )
    capabilities = [
        "repositories",
        "open_source",
        "developer_tools",
        "ai_models",
        "velocity",
        "stars",
    ]
    priority = 5
    cost = 0.0
    credentials_required = False
    collect_interval_seconds = 3600
    strategies = [GitHubTrendingHtmlStrategy(), GitHubSearchApiStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)
