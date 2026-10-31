"""Reddit OSINT Collector adapter (`backend/app/pipeline/collectors/adapters/reddit.py`).

Fetches top/hot posts from high-signal subreddits (r/MachineLearning, r/programming, r/startups, r/cryptodev)
without requiring paid API keys, utilizing public Reddit JSON endpoints, Pullpush, or RSS fallback.
Extracts score, upvote ratio, comment count, author, URL, and body text.
Calculates engagement velocity and alpha score.
"""

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
from app.pipeline.resilience import get_circuit_breaker, get_rate_limiter

logger = get_logger(__name__)

HIGH_SIGNAL_SUBREDDITS: dict[str, str] = {
    "MachineLearning": "ai",
    "programming": "tech",
    "cryptodev": "finance",
    "datascience": "ai",
    "cybersecurity": "tech",
    "technology": "tech",
    "economics": "money",
    "medicine": "health",
}


class RedditJsonStrategy(Strategy):
    name = "reddit_json"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        events: list[RawEvent] = []
        subs = list(HIGH_SIGNAL_SUBREDDITS.keys())
        for country in ctx.countries or []:
            if country == "US":
                subs.extend(["technology", "dev"])

        failures = 0
        headers = {"User-Agent": "AkonitSignalRadar/1.0 (OSINT Collector)"}

        for sub in dict.fromkeys(subs):
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit=25"
            try:
                # Anonymous Reddit JSON is commonly blocked. Keep this fallback
                # bounded so it cannot stall the continuous collection cycle.
                data = await client.get_json(
                    url, headers=headers, retries=0, timeout=3.0
                )
            except Exception as exc:
                failures += 1
                logger.debug("reddit json r/%s failed: %s", sub, exc)
                if failures >= 5:
                    break
                continue

            children = data.get("data", {}).get("children", [])
            for child in children:
                item = child.get("data", {})
                event = self._to_event(item, sub)
                if event:
                    events.append(event)

            if len(events) >= ctx.limit:
                break

        if not events:
            raise SourceUnavailable("reddit json endpoints returned no usable submissions")
        return events[: ctx.limit]

    def _to_event(self, item: dict[str, Any], subreddit: str) -> RawEvent | None:
        title = item.get("title")
        permalink = item.get("permalink")
        if not title or not permalink:
            return None

        created = item.get("created_utc")
        published = datetime.fromtimestamp(float(created), tz=UTC) if created else None
        score = float(item.get("score") or 0)
        upvote_ratio = float(item.get("upvote_ratio") or 1.0)
        comments = float(item.get("num_comments") or 0)
        author = item.get("author", "[deleted]")
        body_text = (item.get("selftext") or item.get("url") or "")[:500]

        # Calculate engagement velocity and alpha score
        age_hours = 1.0
        if published:
            delta = datetime.now(UTC) - published
            age_hours = max(delta.total_seconds() / 3600.0, 0.1)

        velocity = round((score + comments * 3) / age_hours, 2)
        alpha_score = min(round((score * upvote_ratio + comments * 5) / (age_hours + 1) * 0.1, 2), 100.0)

        return RawEvent(
            source_id="reddit_osint",
            external_id=f"reddit_osint:{item.get('id', title[:20])}",
            title=title[:500],
            url=f"https://www.reddit.com{permalink}",
            description=body_text[:400],
            activity=score + comments * 2,
            activity_metric="score_plus_comments",
            category=HIGH_SIGNAL_SUBREDDITS.get(subreddit, "tech"),
            hashtags=[subreddit, "reddit"],
            published_at=published,
            metadata={
                "subreddit": subreddit,
                "score": score,
                "upvote_ratio": upvote_ratio,
                "comments": comments,
                "author": author,
                "engagement_velocity": velocity,
                "alpha_score": alpha_score,
                "strategy": "reddit_json",
            },
        )


class PullPushRedditStrategy(Strategy):
    name = "pullpush_reddit"

    def __init__(self) -> None:
        self._subreddit_offset = 0

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        events: list[RawEvent] = []
        subs = list(HIGH_SIGNAL_SUBREDDITS.keys())
        start = self._subreddit_offset % len(subs)
        batch = [subs[(start + offset) % len(subs)] for offset in range(min(3, len(subs)))]
        self._subreddit_offset = (start + len(batch)) % len(subs)
        per_sub = max(1, min(10, ctx.limit // len(batch)))
        failures = 0

        for sub in batch:
            url = f"https://api.pullpush.io/reddit/search/submission/?subreddit={sub}&size={per_sub}&sort=desc"
            try:
                data = await client.get_json(url, retries=0)
            except Exception:
                failures += 1
                if failures >= 2:
                    break
                continue

            for item in (data.get("data") or [])[:per_sub]:
                title = item.get("title")
                permalink = item.get("permalink")
                if not title or not permalink:
                    continue
                created = item.get("created_utc")
                published = datetime.fromtimestamp(float(created), tz=UTC) if created else None
                score = float(item.get("score") or 0)
                comments = float(item.get("num_comments") or 0)
                
                age_hours = 1.0
                if published:
                    delta = datetime.now(UTC) - published
                    age_hours = max(delta.total_seconds() / 3600.0, 0.1)
                velocity = round((score + comments * 3) / age_hours, 2)
                alpha_score = min(round((score + comments * 5) / (age_hours + 1) * 0.1, 2), 100.0)

                events.append(
                    RawEvent(
                        source_id="reddit_osint",
                        external_id=f"reddit_osint:{item.get('id')}",
                        title=title[:500],
                        url=f"https://www.reddit.com{permalink}",
                        description=(item.get("selftext") or "")[:400],
                        activity=score + comments * 2,
                        activity_metric="score_plus_comments",
                        category=HIGH_SIGNAL_SUBREDDITS.get(sub, "tech"),
                        hashtags=[sub, "reddit"],
                        published_at=published,
                        metadata={
                            "subreddit": sub,
                            "score": score,
                            "comments": comments,
                            "author": item.get("author"),
                            "engagement_velocity": velocity,
                            "alpha_score": alpha_score,
                            "strategy": "pullpush_reddit",
                        },
                    )
                )
        if not events:
            raise SourceUnavailable("pullpush reddit archive returned no submissions")
        return events[: ctx.limit]


@register_source
class RedditOsintAdapter(SourceAdapter):
    source_id = "reddit_osint"
    name = "Reddit OSINT Collector (ML, Programming, Startups, Crypto)"
    type = SourceType.COMMUNITY
    description = (
        "High-signal OSINT collector for r/MachineLearning, r/programming, r/startups, "
        "and r/cryptodev providing engagement velocity and alpha scores."
    )
    capabilities = ["reddit", "machinelearning", "programming", "startups", "cryptodev", "alpha_score", "engagement_velocity"]
    priority = 10
    collect_interval_seconds = 900
    # Anonymous subreddit JSON requests consistently return 403 here. Reddit's
    # other adapter already uses approved OAuth when configured; keep this
    # second collector on the bounded, rotating public archive path only.
    strategies = [PullPushRedditStrategy()]

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
