"""Instagram — Priority #1 social source, credential-gated.

Research findings from live probes:
  * instagram.com/explore/tags/{tag}/ returns ~640KB HTML, but the payload
    does NOT contain media_count, edge_hashtag_to_media, follower_count or
    ld+json — the data is loaded by an authenticated internal GraphQL call.
  * i.instagram.com/api/v1/explore/ -> 404
So reading hashtag data from public HTML would mean circumventing an access
control, which we do not do.

Instead the adapter is fully implemented against the official Meta Graph API
(instagram_basic / instagram_manage_insights). It reports
OPTIONAL_CREDENTIALS with an explicit reason until a token is configured, and
the pipeline keeps running on other sources meanwhile. When a token is present
the adapter activates automatically with no code change.
"""

from __future__ import annotations

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

HASHTAG_SEEDS = [
    "makeup", "skincare", "glassskin", "kbeauty", "reels", "viral",
    "prank", "memes", "fashion", "outfitideas", "beauty", "nails",
    "viralproducts", "smallbusiness", "sidehustle", "tiktokmademebuyit",
]

COUNTRY_TAGS: dict[str, list[str]] = {
    "US": ["viral", "reels"],
    "KR": ["kbeauty", "glassskin", "koreanmakeup"],
    "JP": ["makeup", "skincare"],
    "TR": ["tiktok"],
    "BR": ["beleza", "makeup"],
}


class GraphApiStrategy(Strategy):
    """Official Instagram Graph API for hashtag insights."""

    name = "graph_api"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        token = settings.instagram_access_token
        if not token:
            raise SourceUnavailable(
                "no Instagram Graph API token configured. Public hashtag pages "
                "load data through an authenticated internal call, so we do not "
                "read them. Beauty/fashion signals are still covered by TikTok, "
                "YouTube, X and Google Trends."
            )

        seeds = list(COUNTRY_TAGS.get(ctx.countries[0], [])) if ctx.countries else []
        seeds = seeds or HASHTAG_SEEDS[:10]

        events: list[RawEvent] = []
        for tag in seeds:
            url = (
                f"https://graph.instagram.com/v21.0/ig_hashtag_search"
                f"?user_id={settings.meta_app_id}&q={tag}&access_token={token}"
            )
            data = await client.get_json(url)
            for item in (data.get("data") or []):
                hashtag_id = item.get("id")
                if not hashtag_id:
                    continue
                insights_url = (
                    f"https://graph.instagram.com/v21.0/{hashtag_id}"
                    f"?fields=name,media_count&access_token={token}"
                )
                try:
                    info = await client.get_json(insights_url)
                except SourceUnavailable:
                    continue
                events.append(
                    RawEvent(
                        source_id="instagram",
                        external_id=f"ig:{hashtag_id}",
                        title=f"#{info.get('name', tag)}",
                        url=f"https://www.instagram.com/explore/tags/{tag}/",
                        description=f"Instagram hashtag #{info.get('name', tag)}",
                        activity=float(info.get("media_count") or 0),
                        activity_metric="media_count",
                        category="hashtag",
                        hashtags=[info.get("name", tag)],
                        metadata={"hashtag_id": hashtag_id, "strategy": "graph_api"},
                    )
                )
        if not events:
            raise SourceUnavailable("graph API returned no hashtags")
        return events[: ctx.limit]


@register_source
class InstagramAdapter(SourceAdapter):
    source_id = "instagram"
    name = "Instagram"
    type = SourceType.SOCIAL
    description = (
        "Reels, hashtags and emerging creators via the official Meta Graph API. "
        "Fully implemented; needs a Meta app token to run."
    )
    capabilities = ["reels", "hashtags", "creators", "beauty", "fashion"]
    priority = 5
    collect_interval_seconds = 1800
    credentials_required = True
    credentials_hint = (
        "Needs META_APP_ID + an Instagram Graph API access token "
        "(instagram_basic). Public hashtag pages load their data through an "
        "authenticated internal call, which we do not circumvent."
    )
    strategies = [GraphApiStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        if not settings.instagram_access_token:
            self.health_note_value = self.credentials_hint
        return await run_strategy_cascade(self, ctx, client)