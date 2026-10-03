"""Reddit â€” Priority #1 community source.

Verified public paths:
  * reddit.com/r/{sub}/hot.json          -> 403 for anonymous clients
  * oauth.reddit.com/... without creds  -> 403
  * api.pullpush.io/reddit/search/...   -> OK, full submissions with score and
                                          comment counts, no credentials needed
  * reddit.com/search.rss?q=&sort=new   -> OK, but answers 429 when polled fast

Cascade order: PullPush archive -> Reddit search RSS -> official OAuth.
"""

from __future__ import annotations

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

logger = get_logger(__name__)

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
    "makeup trend",
    "viral product",
    "side hustle",
    "free ai tool",
    "new trend",
    "skincare routine",
]


class PullPushStrategy(Strategy):
    """PullPush public archive: no credentials, gives score + comment counts."""

    name = "pullpush"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        events: list[RawEvent] = []
        subs = list(SUBREDDITS)
        for country in ctx.countries or []:
            subs.extend(COUNTRY_SUBREDDITS.get(country, []))

        failures = 0
        for sub in dict.fromkeys(subs):
            url = (
                "https://api.pullpush.io/reddit/search/submission/"
                f"?subreddit={sub}&size=25&sort=desc"
            )
            try:
                data = await client.get_json(url, retries=0)
            except SourceUnavailable as exc:
                failures += 1
                logger.debug("pullpush r/%s failed: %s", sub, exc)
                if failures >= 4:
                    break
                continue

            for item in (data.get("data") or [])[:25]:
                event = self._to_event(item, sub)
                if event:
                    events.append(event)
            if len(events) >= ctx.limit:
                break

        if not events:
            raise SourceUnavailable("pullpush returned no usable submissions")
        return events[: ctx.limit]

    def _to_event(self, item: dict[str, Any], subreddit: str) -> RawEvent | None:
        title = item.get("title")
        permalink = item.get("permalink")
        if not title or not permalink:
            return None
        created = item.get("created_utc")
        published = (
            datetime.fromtimestamp(float(created), tz=UTC) if created else None
        )
        score = float(item.get("score") or 0)
        comments = float(item.get("num_comments") or 0)
        return RawEvent(
            source_id="reddit",
            external_id=f"reddit:{item.get('id')}",
            title=title[:500],
            url=f"https://www.reddit.com{permalink}",
            description=(item.get("selftext") or "")[:400],
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
                "strategy": "pullpush",
            },
        )


class SearchRssStrategy(Strategy):
    """Reddit search RSS â€” free fallback, paced by the shared rate limiter."""

    name = "search_rss"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        from app.pipeline.collectors.rss_utils import parse_feed

        terms = ctx.keywords[:6] if ctx.keywords else SEARCH_TERMS[:6]
        events: list[RawEvent] = []
        failures = 0

        for term in terms:
            url = (
                "https://www.reddit.com/search.rss"
                f"?q={term.replace(' ', '+')}&sort=new&t=week"
            )
            try:
                xml = await client.get_text(url, retries=1)
            except SourceUnavailable as exc:
                failures += 1
                logger.debug("reddit search rss %r failed: %s", term, exc)
                if failures >= 3:
                    break
                continue

            for item in parse_feed(xml):
                if not item["title"] or not item["link"]:
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
                        metadata={"query": term, "strategy": "search_rss"},
                    )
                )
            if len(events) >= ctx.limit:
                break

        if not events:
            raise SourceUnavailable("reddit search RSS returned no entries")
        return events[: ctx.limit]


class OfficialOAuthStrategy(Strategy):
    """Official Reddit OAuth â€” activates when app credentials are configured."""

    name = "official_oauth"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        if not (settings.reddit_client_id and settings.reddit_client_secret):
            raise SourceUnavailable(
                "no Reddit app credentials configured; the free PullPush "
                "archive already covers this source"
            )
        raise SourceUnavailable(
            "official Reddit OAuth token flow is not configured in this build; "
            "staying on the free archive"
        )


@register_source
class RedditAdapter(SourceAdapter):
    source_id = "reddit"
    name = "Reddit"
    type = SourceType.COMMUNITY
    description = (
        "Emerging topics from curated communities (memes, beauty, pranks, money, "
        "AI, products, fashion) via the free PullPush archive, with Reddit "
        "search RSS as fallback."
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
    collect_interval_seconds = 1800
    strategies = [PullPushStrategy(), SearchRssStrategy(), OfficialOAuthStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)
