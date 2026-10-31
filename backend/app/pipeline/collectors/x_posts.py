"""Official X recent-post search, guarded by an explicit daily read ceiling."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
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


def _state_path() -> Path:
    project_root = Path(__file__).resolve().parents[4]
    return project_root / "logs" / "x-posts-budget.json"


def _read_budget(path: Path | None = None) -> tuple[int, str | None]:
    """Return today's read count and the newest observed post ID."""
    try:
        state = json.loads((path or _state_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0, None
    if not isinstance(state, dict):
        return 0, None
    if state.get("utc_date") != datetime.now(UTC).date().isoformat():
        return 0, None
    try:
        reads = max(int(state.get("reads", 0)), 0)
    except (TypeError, ValueError):
        reads = 0
    since_id = state.get("since_id")
    return reads, str(since_id) if since_id else None


def _write_budget(reads: int, since_id: str | None, path: Path | None = None) -> None:
    target = path or _state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "utc_date": datetime.now(UTC).date().isoformat(),
                "reads": reads,
                "since_id": since_id,
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    temporary.replace(target)


def _build_query(keywords: list[str]) -> str:
    terms: list[str] = []
    for keyword in keywords:
        clean = " ".join(
            keyword.replace('"', "").replace("(", " ").replace(")", " ").split()
        )
        if clean and clean.lower() not in {term.lower() for term in terms}:
            terms.append(clean[:80])
        if len(terms) >= 8:
            break
    if not terms:
        terms = ["breaking news", "new product", "viral trend"]
    query_terms: list[str] = []
    for term in terms:
        candidate_terms = [*query_terms, f'"{term}"']
        candidate = f'({" OR ".join(candidate_terms)}) -is:retweet'
        if len(candidate) > 512:
            break
        query_terms = candidate_terms
    return f'({" OR ".join(query_terms)}) -is:retweet'


class XRecentSearchStrategy(Strategy):
    name = "x_api_v2_recent_search"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        token = settings.x_api_bearer_token
        if not token:
            raise SourceUnavailable("X API Bearer Token is not configured")

        daily_limit = max(settings.x_posts_daily_read_limit, 0)
        reads_today, since_id = _read_budget()
        remaining = daily_limit - reads_today
        # Recent Search has a minimum page size of 10. If fewer than ten
        # billable reads remain, skip the request instead of exceeding the
        # configured daily ceiling on the final page.
        if remaining < 10:
            raise SourceUnavailable(
                f"daily X read limit reached or insufficient for a 10-post page "
                f"({reads_today}/{daily_limit})"
            )

        params: dict[str, Any] = {
            "query": _build_query(ctx.keywords),
            # Recent Search requires a minimum page size of 10. It may return
            # fewer records, which keeps the returned-resource spend bounded.
            "max_results": 10,
            "tweet.fields": "created_at,public_metrics,lang,author_id",
        }
        if since_id:
            params["since_id"] = since_id

        payload = await client.get_json(
            "https://api.x.com/2/tweets/search/recent",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            retries=0,
        )
        if not isinstance(payload, dict):
            raise SourceUnavailable("X API returned an unexpected response")
        if payload.get("errors") and not payload.get("data"):
            raise SourceUnavailable("X API rejected the recent search request")

        posts = payload.get("data") or []
        meta = payload.get("meta") or {}
        newest_id = meta.get("newest_id") or max(
            (str(post.get("id", "")) for post in posts), default=since_id or ""
        )
        # X charges by returned post. Store only this small daily counter and
        # watermark; never persist the bearer token or an API response dump.
        _write_budget(reads_today + len(posts), newest_id or since_id)

        events: list[RawEvent] = []
        for post in posts:
            post_id = str(post.get("id") or "")
            text = str(post.get("text") or "").strip()
            if not post_id or not text:
                continue
            metrics = post.get("public_metrics") or {}
            engagement = sum(
                int(metrics.get(key) or 0)
                for key in ("like_count", "reply_count", "retweet_count", "quote_count")
            )
            created = post.get("created_at")
            published_at = None
            if created:
                try:
                    published_at = datetime.fromisoformat(
                        str(created).replace("Z", "+00:00")
                    )
                    if published_at.tzinfo is None:
                        published_at = published_at.replace(tzinfo=UTC)
                except ValueError:
                    published_at = None
            events.append(
                RawEvent(
                    source_id="x_posts",
                    external_id=f"x:{post_id}",
                    title=text[:500],
                    url=f"https://x.com/i/web/status/{post_id}",
                    description=text[:1800],
                    activity=float(engagement),
                    activity_metric="engagement",
                    category="social",
                    hashtags=[
                        part[1:] for part in text.split() if part.startswith("#")
                    ][:20],
                    published_at=published_at,
                    metadata={
                        "post_id": post_id,
                        "author_id": post.get("author_id"),
                        "language": post.get("lang"),
                        "public_metrics": metrics,
                        "strategy": self.name,
                    },
                )
            )
        return events[: ctx.limit]


@register_source
class XPostsAdapter(SourceAdapter):
    source_id = "x_posts"
    name = "X Posts (official API)"
    type = SourceType.SOCIAL
    description = (
        "Recent public X posts matching active radar keywords. Requires an X API "
        "Bearer Token; reads are pay-per-use and capped by X_POSTS_DAILY_READ_LIMIT."
    )
    capabilities = ["posts", "keyword_search", "engagement", "recent_search"]
    priority = 5
    # Eight scheduled searches per UTC day, with a 10-post page, stays under
    # the default 100-read ceiling while leaving headroom for restarts.
    collect_interval_seconds = 10800
    credentials_required = True
    credentials_hint = (
        "Requires an approved X developer app, prepaid API credits, and "
        "X_API_BEARER_TOKEN. Each returned post is billable."
    )
    cost = "PAY_PER_USE"
    strategies = [XRecentSearchStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)
