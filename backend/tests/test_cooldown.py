"""Tests for NotificationCooldownGuard anti-spam guard."""

from __future__ import annotations

import time
import pytest
from app.notifications.cooldown import NotificationCooldownGuard


def test_cooldown_guard_blocks_burst():
    guard = NotificationCooldownGuard(cooldown_seconds=1.0, maxsize=100)
    
    # First notification should pass
    assert not guard.is_rate_limited("user1", "ai_trend")
    
    # Immediate second notification should be rate-limited
    assert guard.is_rate_limited("user1", "ai_trend")
    
    # Different user or topic should pass
    assert not guard.is_rate_limited("user2", "ai_trend")
    assert not guard.is_rate_limited("user1", "crypto_trend")


def test_cooldown_expires_after_time():
    guard = NotificationCooldownGuard(cooldown_seconds=0.1, maxsize=100)
    assert not guard.is_rate_limited("user1", "topic_x")
    assert guard.is_rate_limited("user1", "topic_x")
    
    time.sleep(0.15)
    
    assert not guard.is_rate_limited("user1", "topic_x")
