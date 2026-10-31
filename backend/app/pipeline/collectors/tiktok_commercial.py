"""Approved TikTok Commercial Content API for public branded-content signals."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
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


_ACCESS_TOKEN: str | None = None
_TOKEN_EXPIRES_AT = 0.0


async def _access_token(client: Any) -> str:
    global _ACCESS_TOKEN, _TOKEN_EXPIRES_AT

    client_key = settings.tiktok_commercial_client_key
    client_secret = settings.tiktok_commercial_client_secret
    if not (client_key and client_secret):
        raise SourceUnavailable(
            "approved TikTok Commercial Content API credentials are not configured"
        )
    if _ACCESS_TOKEN and time.monotonic() < _TOKEN_EXPIRES_AT - 60:
        return _ACCESS_TOKEN

    try:
        response = await client.request(
            "POST",
            "https://open.tiktokapis.com/v2/oauth/token/",
            data={
                "client_key": client_key,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            retries=0,
            raise_on_error=False,
        )
        payload = response.json()
    except Exception as exc:
        raise SourceUnavailable("TikTok commercial API token request failed") from exc

    if response.status_code >= 400:
        raise SourceUnavailable(
            f"TikTok commercial API rejected credentials (HTTP {response.status_code})"
        )
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not token:
        raise SourceUnavailable("TikTok did not return a commercial API token")
    _ACCESS_TOKEN = str(token)
    _TOKEN_EXPIRES_AT = time.monotonic() + max(int(payload.get("expires_in", 7200)), 60)
    return _ACCESS_TOKEN


class CommercialContentStrategy(Strategy):
    name = "tiktok_commercial_content_api"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        token = await _access_token(client)
        today = datetime.now(UTC).date()
        date_range = {
            "min": (today - timedelta(days=2)).strftime("%Y%m%d"),
            "max": today.strftime("%Y%m%d"),
        }
        params = {
            "fields": "id,create_timestamp,create_date,label,brand_names,creator,videos"
        }
        body: dict[str, Any] = {
            "filters": {"content_published_date_range": date_range},
            "max_count": min(max(ctx.limit, 10), 50),
        }
        response = await client.request(
            "POST",
            "https://open.tiktokapis.com/v2/research/adlib/commercial_content/query/",
            params=params,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body,
            retries=0,
            raise_on_error=False,
        )
        try:
            payload = response.json()
        except Exception as exc:
            raise SourceUnavailable(
                "TikTok commercial API returned invalid JSON"
            ) from exc
        if response.status_code >= 400:
            raise SourceUnavailable(
                f"TikTok commercial API rejected the request (HTTP {response.status_code})"
            )
        if not isinstance(payload, dict):
            raise SourceUnavailable(
                "TikTok commercial API returned an unexpected response"
            )
        error = payload.get("error") or {}
        if error.get("code") not in (None, "ok", 0, "0"):
            raise SourceUnavailable("TikTok commercial API rejected the request")

        records = (payload.get("data") or {}).get("commercial_contents") or []
        events: list[RawEvent] = []
        for record in records:
            content_id = str(record.get("id") or "")
            if not content_id:
                continue
            creator = record.get("creator") or {}
            videos = record.get("videos") or []
            video = videos[0] if videos else {}
            brands = [
                str(brand) for brand in (record.get("brand_names") or []) if brand
            ]
            username = str(creator.get("username") or "")
            title_parts = brands or (
                [username] if username else ["TikTok brand content"]
            )
            title = "TikTok brand signal: " + ", ".join(title_parts)
            url = video.get("url") or (
                f"https://www.tiktok.com/@{username}"
                if username
                else "https://www.tiktok.com/"
            )
            timestamp = record.get("create_timestamp")
            published_at = None
            if timestamp:
                try:
                    published_at = datetime.fromtimestamp(float(timestamp), tz=UTC)
                except (TypeError, ValueError, OverflowError, OSError):
                    published_at = None
            elif record.get("create_date"):
                try:
                    published_at = datetime.strptime(
                        str(record["create_date"]), "%Y%m%d"
                    ).replace(tzinfo=UTC)
                except ValueError:
                    published_at = None
            events.append(
                RawEvent(
                    source_id="tiktok_commercial",
                    external_id=f"tiktok-commercial:{content_id}",
                    title=title[:500],
                    url=str(url),
                    description=str(
                        record.get("label") or "Public branded-content disclosure"
                    ),
                    activity=0.0,
                    activity_metric="commercial_posts",
                    category="commercial",
                    hashtags=[*brands[:10], "tiktok", "brand-signal"],
                    thumbnail=video.get("cover_image_url"),
                    published_at=published_at,
                    metadata={
                        "creator": username,
                        "brands": brands,
                        "label": record.get("label"),
                        "video_id": video.get("id"),
                        "video_status": video.get("status"),
                        "strategy": self.name,
                    },
                )
            )
        return events[: ctx.limit]


@register_source
class TikTokCommercialAdapter(SourceAdapter):
    source_id = "tiktok_commercial"
    name = "TikTok Commercial Content"
    type = SourceType.SOCIAL
    description = (
        "Official public branded-content feed. Approval is required and the current "
        "creator-country dataset covers EEA countries (excluding the UK and "
        "Switzerland)."
    )
    capabilities = ["branded_content", "advertising", "brands", "creators"]
    priority = 6
    collect_interval_seconds = 14400
    credentials_required = True
    credentials_hint = (
        "Requires an approved TikTok Commercial Content API application; current "
        "creator-country coverage is EEA countries, excluding the UK and Switzerland."
    )
    cost = "APPROVAL_REQUIRED"
    strategies = [CommercialContentStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)
