"""Multi-channel webhook notification dispatchers (Discord, Slack, and Custom Webhooks).

Formats high-alpha signals (`critical` priority or `UNICORN_SIGNAL` status) into rich cards
with title, alpha score, monetization strategy, and direct links.
"""

from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.webhook_url import validate_public_https_url
from app.models import NotificationDelivery, Signal, UserProfile
from app.models.enums import DeliveryStatus, NotificationChannel

logger = get_logger(__name__)


def format_webhook_card(signal: Signal, radar_name: str | None = None) -> dict:
    """Format high-alpha signal into rich card structures."""
    status_str = signal.status.value if hasattr(signal.status, "value") else str(signal.status)
    alpha_score = getattr(signal, "strength", 0.0)
    monetization = getattr(signal, "ai_category", None) or signal.category or "High-Growth Alpha Opportunity"
    link = f"{settings.frontend_url}/signals/{signal.id}"
    
    # Discord Embed Format
    discord_embed = {
        "title": f"🚨 HIGH-ALPHA SIGNAL: {signal.title[:100]}",
        "url": link,
        "color": 0xFF4500,  # Orange-Red highlight for high alpha
        "fields": [
            {"name": "Status / Priority", "value": f"{status_str} / {getattr(signal, 'ai_priority', 'normal')}", "inline": True},
            {"name": "Alpha Score", "value": f"{alpha_score:.1f}/100", "inline": True},
            {"name": "Monetization Strategy", "value": str(monetization), "inline": False},
            {"name": "Source", "value": f"{signal.flag or ''} {signal.country_name or signal.country_code or 'Global'} · {signal.source_id}", "inline": True},
            {"name": "Growth", "value": f"+{signal.growth:.0f}%", "inline": True},
        ],
        "footer": {"text": f"Akonit Signal Radar {f'• Radar: {radar_name}' if radar_name else ''}"},
    }
    if radar_name:
        discord_embed["description"] = f"Triggered by Radar: **{radar_name}**"

    # Slack Block Kit / Attachment Format
    slack_payload = {
        "text": f"🚨 *HIGH-ALPHA SIGNAL: {signal.title[:100]}*",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🚨 *<{link}|{signal.title[:100]}>*\n"
                            f"• *Status:* `{status_str}`\n"
                            f"• *Alpha Score:* `{alpha_score:.1f}/100`\n"
                            f"• *Monetization:* {monetization}\n"
                            f"• *Source:* {signal.source_id} ({signal.country_code or 'Global'})\n"
                            f"• *Growth:* `+{signal.growth:.0f}%`"
                }
            }
        ]
    }

    # Generic Webhook Payload
    generic_payload = {
        "event": "high_alpha_signal",
        "signal_id": signal.id,
        "title": signal.title,
        "status": status_str,
        "priority": getattr(signal, "ai_priority", "normal"),
        "alpha_score": alpha_score,
        "monetization": monetization,
        "growth": signal.growth,
        "source": signal.source_id,
        "country": signal.country_code,
        "url": link,
        "radar": radar_name,
    }

    return {
        "discord": {"embeds": [discord_embed]},
        "slack": slack_payload,
        "generic": generic_payload,
    }


async def dispatch_webhook_notification(
    session: AsyncSession,
    delivery: NotificationDelivery,
    signal: Signal,
) -> None:
    """Dispatch webhook notification to Discord, Slack, or generic custom webhooks."""
    # Retrieve webhook URL from UserProfile or delivery payload / settings
    profile = (
        await session.execute(
            select(UserProfile).where(UserProfile.user_id == delivery.user_id)
        )
    ).scalar_one_or_none()

    webhook_url = None
    if delivery.payload and isinstance(delivery.payload, dict):
        webhook_url = delivery.payload.get("webhook_url")

    if not webhook_url and profile and isinstance(profile.preferences, dict):
        webhook_url = profile.preferences.get("webhook_url")

    if not webhook_url:
        # Check global environment setting as fallback
        if delivery.channel == NotificationChannel.DISCORD:
            webhook_url = getattr(settings, "discord_webhook_url", None)
        elif delivery.channel == NotificationChannel.SLACK:
            webhook_url = getattr(settings, "slack_webhook_url", None)
        elif delivery.channel == NotificationChannel.WEBHOOK:
            webhook_url = getattr(settings, "custom_webhook_url", None)

    if not webhook_url:
        delivery.status = DeliveryStatus.SKIPPED
        delivery.error = f"Webhook URL not configured for channel {delivery.channel}"
        return

    webhook_url = await validate_public_https_url(webhook_url)

    cards = format_webhook_card(signal, delivery.payload.get("radar") if delivery.payload else None)

    if delivery.channel == NotificationChannel.DISCORD:
        payload = cards["discord"]
    elif delivery.channel == NotificationChannel.SLACK:
        payload = cards["slack"]
    else:
        payload = cards["generic"]

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            response = await client.post(webhook_url, json=payload)
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Webhook request failed ({type(exc).__name__})"
        ) from None
    if not response.is_success:
        raise RuntimeError(f"Webhook dispatch failed with status {response.status_code}")
        
    delivery.status = DeliveryStatus.SENT
    logger.info("Successfully dispatched webhook (%s)", delivery.channel)
