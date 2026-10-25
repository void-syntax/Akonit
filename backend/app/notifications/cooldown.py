"""Notification Cooldown & Anti-Spam Guard (`backend/app/notifications/cooldown.py`).

Prevents alert fatigue and rate-limits notification bursts per user/radar
using an in-memory sliding window and LRU cache.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from app.core.logging import get_logger

logger = get_logger("app.notifications.cooldown")


class NotificationCooldownGuard:
    """Memory-safe sliding window cooldown tracker for notification channels."""

    def __init__(self, cooldown_seconds: float = 60.0, maxsize: int = 10_000) -> None:
        self.cooldown_seconds = cooldown_seconds
        self.maxsize = maxsize
        # key (user_id:signal_hash) -> monotonic timestamp
        self._store: OrderedDict[str, float] = OrderedDict()

    def is_rate_limited(self, user_id: str, topic_key: str) -> bool:
        """Return True if notification for this user and topic is within cooldown."""
        key = f"{user_id}:{topic_key}"
        now = time.monotonic()

        if key in self._store:
            last_sent = self._store[key]
            if now - last_sent < self.cooldown_seconds:
                return True
            self._store.move_to_end(key)
        
        self._store[key] = now
        if len(self._store) > self.maxsize:
            self._store.popitem(last=False)
        return False

    def clear(self) -> None:
        self._store.clear()


_guard: NotificationCooldownGuard | None = None


def get_cooldown_guard() -> NotificationCooldownGuard:
    global _guard
    if _guard is None:
        _guard = NotificationCooldownGuard(cooldown_seconds=60.0, maxsize=10_000)
        logger.info("NotificationCooldownGuard initialized (cooldown=60s, maxsize=10000)")
    return _guard
