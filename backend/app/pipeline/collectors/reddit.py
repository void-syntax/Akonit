"""Reddit â€” Priority #1 community source.

Verified public paths:
  * reddit.com/r/{sub}/hot.json          -> 403 for anonymous clients
  * oauth.reddit.com/... without creds  -> 403
  * reddit.com/search.rss?q=&sort=new   -> works intermittently, answers 429
                                          when polled too quickly

Cascade order: official OAuth -> bounded public search RSS.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
import time
from urllib.parse import quote_plus

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
from app.pipeline.normalization.normalizer import tokenize

logger = get_logger(__name__)

_REDDIT_ACCESS_TOKEN: str | None = None
_REDDIT_TOKEN_EXPIRES_AT = 0.0

# Communities mapped to the signal categories Signal Radar targets.
SUBREDDITS: dict[str, str] = {
    "Memes": "memes",
    "MakeupAddiction": "beauty",
    "SkincareAddiction": "beauty",
    "AsianBeauty": "beauty",
    "HaircareScience": "beauty",
    "Nails": "beauty",
    "Damnthatsassholes": "pranks",
    "funny": "memes",
    "Entrepreneur": "money",
    "SideHustle": "money",
    "EtsySellers": "money",
    "dropshipping": "money",
    "passive_income": "money",
    "ChatGPT": "ai",
    "LocalLLaMA": "ai",
    "artificial": "ai",
    "SaaS": "tech",
    "startups": "products",
    "ProductHunt": "products",
    "fashion": "fashion",
    "streetwear": "fashion",
}

COUNTRY_SUBREDDITS: dict[str, list[str]] = {
    "KR": ["kbeauty", "KoreanBeauty"],
    "JP": ["japanlife"],
    "US": ["MakeupAddiction"],
    "TR": ["AskTurkey"],
    "AE": ["DubaiPetrolHeads"],
}

SEARCH_TERMS = [
    "new trend", "viral product", "free ai tool", "side hustle",
    "gaming trend", "health research", "climate technology", "crypto",
    "cybersecurity", "creator economy", "startup launch", "science discovery",
    "fashion trend", "skincare routine", "makeup trend", "food trend",
    "travel trend", "music trend", "consumer gadget", "electric vehicles",
]
_QUERY_STOPWORDS = {"new", "latest", "free", "best", "top", "or"}


def _matched_query_terms(query: str, text: str) -> list[str]:
    """Return discriminative query words present in a search result.

    Reddit RSS sometimes returns loosely related or personalized results. Keep
    a cheap local relevance gate so those posts do not enter the signal store
    under an unrelated search query.
    """
    query_terms = list(dict.fromkeys(t for t in tokenize(query) if t not in _QUERY_STOPWORDS))
    if not query_terms:
        return []
    result_terms = set(tokenize(text))
    matched = [term for term in query_terms if term in result_terms]
    required = max(1, (len(query_terms) + 1) // 2)
    return matched if len(matched) >= required else []


def _reddit_query_title_matches(query: str, title: str) -> list[str]:
    """Require a query word in the title; snippets can contain unrelated text."""
    return _matched_query_terms(query, title)


def _rotated(items: list[str], count: int, slot_seconds: int = 1800) -> list[str]:
    """Rotate bounded queries so early list entries do not monopolize each run."""
    if not items:
        return []
    start = int(time.time() // slot_seconds) % len(items)
    return [items[(start + i) % len(items)] for i in range(min(count, len(items)))]


class SearchRssStrategy(Strategy):
    """Reddit search RSS â€” free fallback, paced by the shared rate limiter."""

    name = "search_rss"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        from app.pipeline.collectors.rss_utils import parse_feed

        # PullPush/archive is frequently unavailable; try the lightweight RSS
        # fallback across a few rotated terms before declaring the source down.
        terms = _rotated(ctx.keywords or SEARCH_TERMS, 4)
        events: list[RawEvent] = []
        failures = 0

        for term in terms:
            url = (
                "https://www.reddit.com/search.rss"
                f"?q={quote_plus(term)}&sort=new&t=day"
            )
            try:
                xml = await client.get_text(url, retries=0, timeout=3.0)
            except SourceUnavailable as exc:
                failures += 1
                logger.debug("reddit search rss %r failed: %s", term, exc)
                if failures >= 3:
                    break
                continue

            for item in parse_feed(xml):
                if not item["title"] or not item["link"]:
                    continue
                # Search RSS snippets often contain incidental query words.
                # Require relevance in the headline itself before storing it.
                matched_terms = _reddit_query_title_matches(term, item["title"])
                if not matched_terms:
                    continue
                events.append(
                    RawEvent(
                        source_id="reddit",
                        external_id=(
                            f"reddit-search:{item['link'].rsplit('/', 1)[-1][:12]}"
                        ),
                        title=item["title"][:500],
                        url=item["link"],
                        description=(item["description"] or "")[:400],
                        activity=0.0,
                        activity_metric="score_plus_comments",
                        category="discussion",
                        hashtags=item["tags"],
                        published_at=item["published"],
                        metadata={
                            "query": term,
                            "matched_query_terms": matched_terms,
                            "strategy": "search_rss",
                        },
                    )
                )
            if len(events) >= ctx.limit:
                break

        if not events:
            raise SourceUnavailable("reddit search RSS returned no entries")
        return events[: ctx.limit]


class OfficialOAuthStrategy(Strategy):
    """Approved application-only Reddit OAuth with a short-lived token cache."""

    name = "official_oauth"

    def __init__(self) -> None:
        self._subreddit_offset = 0

    async def _access_token(self, client: Any) -> str:
        global _REDDIT_ACCESS_TOKEN, _REDDIT_TOKEN_EXPIRES_AT

        if not (settings.reddit_client_id and settings.reddit_client_secret):
            raise SourceUnavailable("Reddit OAuth credentials are not configured")
        if (
            not settings.reddit_user_agent.strip()
            or settings.reddit_user_agent == "SignalRadar/0.1"
            or "your_reddit_username" in settings.reddit_user_agent
        ):
            raise SourceUnavailable(
                "set REDDIT_USER_AGENT to a descriptive app name and contact"
            )
        if _REDDIT_ACCESS_TOKEN and time.monotonic() < _REDDIT_TOKEN_EXPIRES_AT - 60:
            return _REDDIT_ACCESS_TOKEN

        try:
            response = await client.request(
                "POST",
                "https://www.reddit.com/api/v1/access_token",
                auth=(settings.reddit_client_id, settings.reddit_client_secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": settings.reddit_user_agent},
                retries=0,
                raise_on_error=False,
            )
            payload = response.json()
        except Exception as exc:
            raise SourceUnavailable("Reddit OAuth token request failed") from exc

        if response.status_code >= 400:
            raise SourceUnavailable(
                f"Reddit OAuth rejected the app (HTTP {response.status_code})"
            )
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not token:
            error = payload.get("error") if isinstance(payload, dict) else None
            detail = str(error)[:100] if error else "no token returned"
            raise SourceUnavailable(f"Reddit OAuth rejected the app ({detail})")
        _REDDIT_ACCESS_TOKEN = str(token)
        _REDDIT_TOKEN_EXPIRES_AT = time.monotonic() + max(
            int(payload.get("expires_in", 3600)), 60
        )
        return _REDDIT_ACCESS_TOKEN

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        if not (settings.reddit_client_id and settings.reddit_client_secret):
            raise SourceUnavailable("no approved Reddit app credentials configured")
        if (
            not settings.reddit_user_agent.strip()
            or settings.reddit_user_agent == "SignalRadar/0.1"
            or "your_reddit_username" in settings.reddit_user_agent
        ):
            raise SourceUnavailable(
                "set REDDIT_USER_AGENT to a descriptive app name and contact"
            )

        token = await self._access_token(client)
        subreddits = list(SUBREDDITS)
        for country in ctx.countries or []:
            subreddits.extend(COUNTRY_SUBREDDITS.get(country, []))
        subreddits = list(dict.fromkeys(subreddits))
        if not subreddits:
            raise SourceUnavailable("no Reddit communities configured")

        start = self._subreddit_offset % len(subreddits)
        batch = [
            subreddits[(start + offset) % len(subreddits)]
            for offset in range(min(5, len(subreddits)))
        ]
        self._subreddit_offset = (start + len(batch)) % len(subreddits)
        per_subreddit = max(1, min(5, ctx.limit // len(batch)))
        events: list[RawEvent] = []
        failures = 0
        for subreddit in batch:
            try:
                payload = await client.get_json(
                    f"https://oauth.reddit.com/r/{subreddit}/new.json",
                    params={"limit": per_subreddit, "raw_json": 1},
                    headers={
                        "Authorization": f"Bearer {token}",
                        "User-Agent": settings.reddit_user_agent,
                    },
                    retries=0,
                )
            except Exception as exc:
                failures += 1
                logger.info(
                    "official Reddit fetch failed for r/%s (%s)",
                    subreddit,
                    type(exc).__name__,
                )
                continue

            children = (payload.get("data") or {}).get("children") or []
            for child in children:
                item = child.get("data") or {}
                event = _reddit_event(item, subreddit)
                if event:
                    events.append(event)

        if not events:
            raise SourceUnavailable(
                "official Reddit API returned no posts"
                if failures == 0
                else "official Reddit API requests failed"
            )
        return events[: ctx.limit]


def _reddit_event(item: dict[str, Any], subreddit: str) -> RawEvent | None:
    title = item.get("title")
    permalink = item.get("permalink")
    if not title or not permalink:
        return None
    created = item.get("created_utc")
    published = datetime.fromtimestamp(float(created), tz=UTC) if created else None
    score = float(item.get("score") or 0)
    comments = float(item.get("num_comments") or 0)
    return RawEvent(
        source_id="reddit",
        external_id=f"reddit:{item.get('id', title[:20])}",
        title=str(title)[:500],
        url=f"https://www.reddit.com{permalink}",
        description=str(item.get("selftext") or item.get("url") or "")[:400],
        activity=score + comments * 2,
        activity_metric="score_plus_comments",
        category=SUBREDDITS.get(subreddit, "discussion"),
        hashtags=[subreddit],
        published_at=published,
        metadata={
            "subreddit": subreddit,
            "score": score,
            "comments": comments,
            "author": item.get("author"),
            "flair": item.get("link_flair_text"),
            "strategy": "official_oauth",
        },
    )


@register_source
class RedditAdapter(SourceAdapter):
    source_id = "reddit"
    name = "Reddit"
    type = SourceType.COMMUNITY
    description = (
        "Emerging topics from curated communities (memes, beauty, pranks, money, "
        "AI, products, fashion). Uses approved Reddit OAuth when configured, then "
        "a bounded public search RSS fallback."
    )
    capabilities = [
        "memes",
        "discussions",
        "products",
        "ai",
        "money",
        "beauty",
        "community",
        "score_velocity",
    ]
    priority = 3
    collect_interval_seconds = 900
    credentials_hint = "Optional: approved Reddit Data API app credentials enable official OAuth; a bounded public RSS fallback remains available."
    strategies = [OfficialOAuthStrategy(), SearchRssStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        result = await run_strategy_cascade(self, ctx, client)
        # run_strategy_cascade returns at the first successful fallback. Make
        # sure the adapter is the one recorded on events, independent of the
        # implementation strategy that supplied them.
        for event in result.events:
            event.source_id = self.source_id
        return result
