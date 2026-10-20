"""Tests for multi-channel webhook dispatcher."""

from __future__ import annotations

import pytest

from app.models import Signal
from app.models.enums import SignalStatus
from app.notifications.webhook_dispatcher import format_webhook_card


def test_format_webhook_card() -> None:
    signal = Signal(
        id="sig_test_123",
        title="Revolutionary Quantum AI Model Released",
        description="Quantum computing meets autonomous AI agents.",
        category="AI & ML",
        growth=1250.0,
        strength=92.5,
        status=SignalStatus.UNICORN_SIGNAL,
        source_id="hacker_news",
        country_code="US",
        flag="🇺🇸",
    )
    cards = format_webhook_card(signal, radar_name="Top AI Radar")

    assert "discord" in cards
    assert "slack" in cards
    assert "generic" in cards

    discord_embed = cards["discord"]["embeds"][0]
    assert "Revolutionary Quantum AI Model" in discord_embed["title"]
    assert discord_embed["color"] == 0xFF4500
    assert any(f["name"] == "Alpha Score" and f["value"] == "92.5/100" for f in discord_embed["fields"])

    slack = cards["slack"]
    assert "HIGH-ALPHA SIGNAL" in slack["text"]
    assert len(slack["blocks"]) > 0

    generic = cards["generic"]
    assert generic["signal_id"] == "sig_test_123"
    assert generic["alpha_score"] == 92.5
    assert generic["radar"] == "Top AI Radar"
