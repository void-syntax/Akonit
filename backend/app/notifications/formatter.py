"""Notification rendering.

Per the brief, notifications stay short and factual: status, country, source,
title, growth, first seen and a link. No long text, no summaries.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.config import settings
from app.models import Signal

STATUS_EMOJI = {
    "NEW": "🆕",
    "RISING": "📈",
    "BREAKOUT": "🚨",
    "FADING": "💤",
}

STATUS_HEADLINE = {
    "NEW": "NEW SIGNAL",
    "RISING": "RISING SIGNAL",
    "BREAKOUT": "BREAKOUT",
    "FADING": "FADING",
}


def time_ago(value: datetime | None) -> str:
    if value is None:
        return "unknown"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    minutes = max((datetime.now(UTC) - value).total_seconds() / 60, 0)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{int(minutes)} min ago"
    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)} h ago"
    return f"{int(hours // 24)} d ago"


def format_growth(growth: float) -> str:
    if growth > 0:
        return f"+{growth:.0f}%"
    return f"{growth:.0f}%"


def signal_line(signal: Signal) -> str:
    """'🇰🇷 Korea · TikTok'"""
    flag = signal.flag or ""
    country = signal.country_name or signal.country_code or "Global"
    return f"{flag} {country} · {signal.source_id}".strip()


def format_signal_alert(signal: Signal, radar_name: str | None = None) -> str:
    emoji = STATUS_EMOJI.get(signal.status.value, "🔔")
    headline = STATUS_HEADLINE.get(signal.status.value, "SIGNAL")
    lines = [
        f"{emoji} {headline}",
        signal_line(signal),
        "",
        signal.title[:120],
        f"Growth: {format_growth(signal.growth)}   ·   "
        f"First seen: {time_ago(signal.first_seen_at)}",
    ]
    if radar_name:
        lines.append(f"Radar: {radar_name}")
    link = f"{settings.frontend_url}/signals/{signal.id}"
    lines.append("")
    lines.append(f"[Open Signal]({link})")
    return "\n".join(lines)


def format_web_push(signal: Signal, radar_name: str | None = None) -> dict:
    """Compact browser-push payload."""
    growth = format_growth(signal.growth)
    return {
        "title": f"{STATUS_EMOJI.get(signal.status.value, '🔔')} "
        f"{signal.title[:70]}",
        "body": f"{signal_line(signal)} · {growth} · "
        f"{time_ago(signal.first_seen_at)}",
        "tag": signal.id,
        "data": {
            "signal_id": signal.id,
            "url": f"{settings.frontend_url}/signals/{signal.id}",
            "radar": radar_name,
        },
    }