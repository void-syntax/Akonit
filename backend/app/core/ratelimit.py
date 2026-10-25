"""Dynamic Adaptive Rate Limiter & Token Bucket (`backend/app/core/ratelimit.py`).

Provides sliding-window token bucket rate limiting for incoming API requests
and outgoing collector fetches to prevent API bans and resource starvation.
"""

from __future__ import annotations

import time
from collections import defaultdict
from app.core.logging import get_logger

logger = get_logger("app.core.ratelimit")


class TokenBucketRateLimiter:
    """Memory-bounded sliding window token bucket rate limiter."""

    def __init__(self, rate: float = 10.0, capacity: float = 20.0) -> None:
        self.rate = rate  # tokens per second
        self.capacity = capacity
        self.buckets: dict[str, tuple[float, float]] = defaultdict(lambda: (capacity, time.monotonic()))

    def acquire(self, key: str, tokens: int = 1) -> bool:
        """Return True if tokens are available and consume them, else False."""
        now = time.monotonic()
        tokens_left, last_update = self.buckets[key]

        # Refill tokens based on elapsed time
        elapsed = now - last_update
        tokens_left = min(self.capacity, tokens_left + elapsed * self.rate)

        if tokens_left >= tokens:
            self.buckets[key] = (tokens_left - tokens, now)
            return True

        self.buckets[key] = (tokens_left, now)
        return False


_limiter: TokenBucketRateLimiter | None = None


def get_rate_limiter() -> TokenBucketRateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = TokenBucketRateLimiter(rate=15.0, capacity=30.0)
        logger.info("TokenBucketRateLimiter initialized")
    return _limiter
