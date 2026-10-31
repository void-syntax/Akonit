"""Mastodon Trends — публичный API, без авторизации, без ключа.

Endpoint docs: https://docs.joinmastodon.org/methods/trends/

Запрашиваем сразу несколько крупных инстансов для более широкого охвата.
Каждый инстанс имеет независимую базу пользователей и свои тренды.
API полностью публичный, rate-limit зависит от конкретного инстанса.

Возвращает trending hashtags с историей использования по дням.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
import asyncio
import re
from html import unescape

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

# Major Mastodon instances with high activity and public APIs
DEFAULT_MASTODON_INSTANCES = [
    "mastodon.social", "fosstodon.org", "infosec.exchange", "hachyderm.io"
]

# Recurring calendar / lifestyle tags are commonly ranked by an instance's
# local trends API, but add little value to a broad early-warning feed.
LOW_SIGNAL_TAGS = {
    "tgif",
    "friday",
    "fursuitfriday",
    "viernesdeescritorio",
    "sextaserie",
    "thursdayfivelist",
    "lastfourwatched",
}


def mastodon_instances() -> list[str]:
    """Read bounded, hostname-only instances from environment settings."""
    values = [v.strip().lower() for v in settings.mastodon_instances.split(",")]
    hosts: list[str] = []
    for host in values:
        if not host or host in hosts or len(host) > 253:
            continue
        if not re.fullmatch(r"[a-z0-9.-]+", host) or host.startswith(".") or host.endswith("."):
            continue
        if ".." in host or any(not label or label.startswith("-") or label.endswith("-") for label in host.split(".")):
            continue
        hosts.append(host)
        if len(hosts) >= 6:
            break
    return hosts or DEFAULT_MASTODON_INSTANCES


def _parse_tag_uses(history: list[dict]) -> float:
    """Sum the most recent 3 days of tag usage as activity metric."""
    total = 0.0
    for entry in (history or [])[:3]:
        try:
            total += float(entry.get("uses") or 0)
        except (TypeError, ValueError):
            pass
    return total


def _growth_velocity(history: list[dict]) -> float:
    """Return ratio of today vs. 7-day average. Values > 1 indicate spike."""
    if not history or len(history) < 2:
        return 1.0
    try:
        today = float(history[0].get("uses") or 0)
        rest = [float(e.get("uses") or 0) for e in history[1:]]
        avg_rest = sum(rest) / len(rest) if rest else 1.0
        if avg_rest <= 0:
            return 1.0
        return today / avg_rest
    except (TypeError, ValueError):
        return 1.0


def _is_early_tag(history: list[dict], *, min_today_uses: int = 25) -> bool:
    """Keep tags with meaningful activity today and growth over their baseline."""
    if not history:
        return False
    try:
        today_uses = float(history[0].get("uses") or 0)
    except (TypeError, ValueError):
        return False
    return today_uses >= min_today_uses and _growth_velocity(history) >= 1.5


class MastodonTrendingTagsStrategy(Strategy):
    """Fetch trending hashtags from public Mastodon instances."""

    name = "trending_tags"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        events: list[RawEvent] = []
        seen: set[str] = set()
        successes = 0

        instances = mastodon_instances()
        semaphore = asyncio.Semaphore(3)

        async def fetch_instance(instance: str):
            url = f"https://{instance}/api/v1/trends/tags?limit=20"
            try:
                async with semaphore:
                    data = await client.get_json(url, retries=0, timeout=5.0)
            except Exception as exc:
                logger.debug("mastodon %s trends/tags failed: %s", instance, type(exc).__name__)
                return instance, None
            return instance, data

        results = await asyncio.gather(*(fetch_instance(host) for host in instances))
        for instance, data in results:
            if not isinstance(data, list):
                continue
            successes += 1
            for tag in data:
                name = tag.get("name") or ""
                if not name or name.casefold() in LOW_SIGNAL_TAGS or name.lower() in seen:
                    continue
                seen.add(name.lower())

                history = tag.get("history") or []
                if not _is_early_tag(history):
                    continue
                activity = _parse_tag_uses(history)
                velocity = _growth_velocity(history)

                events.append(
                    RawEvent(
                        source_id="mastodon",
                        external_id=f"mastodon:tag:{name.lower()}",
                        title=f"#{name}",
                        url=f"https://{instance}/tags/{name}",
                        description=(
                            f"Trending on Mastodon: #{name} — "
                            f"{int(activity):,} uses in 3 days"
                        ),
                        activity=activity,
                        activity_metric="uses_3d",
                        category="hashtag",
                        hashtags=[name],
                        metadata={
                            "instance": instance,
                            "velocity_ratio": round(velocity, 2),
                            "history": history[:3],
                            "strategy": "trending_tags",
                        },
                    )
                )

            if len(events) >= ctx.limit:
                break

        if not successes:
            raise SourceUnavailable(
                "all Mastodon instances failed to return trending tags"
            )
        if not events:
            raise SourceUnavailable("mastodon trending tags: no events parsed")

        # Sort by activity descending; spiky tags float to top
        events.sort(key=lambda e: e.activity, reverse=True)
        return events[: ctx.limit]


class MastodonTrendingStatusesStrategy(Strategy):
    """Fetch trending statuses (posts) from public Mastodon instances."""

    name = "trending_statuses"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        events: list[RawEvent] = []
        seen: set[str] = set()

        for instance in mastodon_instances()[:2]:  # cap requests per cycle
            url = f"https://{instance}/api/v1/trends/statuses?limit=20"
            try:
                data = await client.get_json(url, retries=0, timeout=5.0)
            except Exception as exc:
                logger.debug(
                    "mastodon %s trends/statuses failed: %s", instance, exc
                )
                continue

            if not isinstance(data, list):
                continue

            for status in data:
                status_id = status.get("id")
                if not status_id or status_id in seen:
                    continue
                seen.add(status_id)

                account = (status.get("account") or {}).get("acct", "")
                content_raw = status.get("content") or ""
                # Strip HTML tags crudely for description
                import re
                content = unescape(re.sub(r"<[^>]+>", " ", content_raw)).strip()[:400]
                if not content:
                    continue

                reblogs = float(status.get("reblogs_count") or 0)
                favourites = float(status.get("favourites_count") or 0)
                replies = float(status.get("replies_count") or 0)
                activity = reblogs * 3 + favourites + replies * 2

                created_at = status.get("created_at")
                try:
                    published = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    ) if created_at else None
                except ValueError:
                    published = None

                tags = [t.get("name", "") for t in (status.get("tags") or [])]
                url_val = status.get("url") or f"https://{instance}/@{account}/{status_id}"

                events.append(
                    RawEvent(
                        source_id="mastodon",
                        external_id=f"mastodon:status:{status_id}",
                        title=content[:120],
                        url=url_val,
                        description=content,
                        activity=activity,
                        activity_metric="engagement",
                        category="social_post",
                        hashtags=tags,
                        published_at=published,
                        metadata={
                            "instance": instance,
                            "account": account,
                            "reblogs": reblogs,
                            "favourites": favourites,
                            "replies": replies,
                            "strategy": "trending_statuses",
                        },
                    )
                )

            if len(events) >= ctx.limit:
                break

        if not events:
            raise SourceUnavailable("mastodon trending statuses: no events parsed")
        events.sort(key=lambda e: e.activity, reverse=True)
        return events[: ctx.limit]


@register_source
class MastodonTrendsAdapter(SourceAdapter):
    source_id = "mastodon"
    name = "Mastodon Trends"
    type = SourceType.SOCIAL
    description = (
        "Trending hashtags and viral posts from the Mastodon federated network. "
        "Uses the public trends API — no auth, no API key required. "
        "Aggregates data from multiple major instances for broad coverage."
    )
    capabilities = [
        "hashtags",
        "social_posts",
        "tech_community",
        "open_source",
        "decentralized",
        "trends",
    ]
    priority = 20
    cost = 0.0
    credentials_required = False
    collect_interval_seconds = 600
    strategies = [MastodonTrendingTagsStrategy(), MastodonTrendingStatusesStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)
