"""Tests for TokenBucketRateLimiter module."""

from __future__ import annotations

import pytest
from app.core.ratelimit import TokenBucketRateLimiter


def test_token_bucket_rate_limiter():
    limiter = TokenBucketRateLimiter(rate=1.0, capacity=2.0)
    
    assert limiter.acquire("user1", 1) is True
    assert limiter.acquire("user1", 1) is True
    assert limiter.acquire("user1", 1) is False  # Bucket empty
