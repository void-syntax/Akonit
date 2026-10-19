"""Production-grade Circuit Breaker and Rate Limiter for external data collectors.

Circuit Breaker:
- CLOSED  → normal operation, failures are counted
- OPEN    → circuit tripped after 3 consecutive failures; all calls are blocked for 5 min
- HALF_OPEN → single probe request allowed after cooldown; success closes, failure re-opens

Rate Limiter:
- Token-bucket algorithm per source
- Per-source configurable rates (tokens refill at `rate_per_minute / 60` per second)
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────── constants ──

# Failure threshold before circuit opens
DEFAULT_FAILURE_THRESHOLD: int = 3
# Seconds the circuit stays OPEN before probing again (5 minutes)
DEFAULT_OPEN_SECONDS: float = 300.0

# Default per-source rate limits (max requests per minute)
SOURCE_RATE_LIMITS: dict[str, float] = {
    "github": 30.0,
    "huggingface": 60.0,
    "hackernews": 60.0,
    "hackernews_rss": 60.0,
    "reddit": 30.0,
    "stackoverflow": 30.0,
    "devto": 30.0,
    "npm": 60.0,
    "lobsters": 60.0,
    "producthunt": 30.0,
    "rss_news": 60.0,
    "techcrunch": 60.0,
    "bloomberg": 60.0,
    "google_trends": 10.0,
    "google_news_trends": 10.0,
    "youtube": 20.0,
    "tiktok": 20.0,
    "instagram": 20.0,
    "x_trends": 15.0,
    # Default for unknowns
    "_default": 30.0,
}


# ─────────────────────────────────────────────────────────── circuit breaker ──

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Three-state circuit breaker tied to one named source.

    Usage::

        cb = CircuitBreaker("github")
        if cb.is_open():
            return []          # circuit tripped – skip call
        try:
            result = await do_request()
            cb.record_success()
        except Exception:
            cb.record_failure()
            raise
    """

    def __init__(
        self,
        source_id: str,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        open_seconds: float = DEFAULT_OPEN_SECONDS,
    ) -> None:
        self.source_id = source_id
        self.failure_threshold = failure_threshold
        self.open_seconds = open_seconds

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._opened_at: float | None = None  # monotonic time

    # ── public read ──────────────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        """Return current state, transitioning to HALF_OPEN if cooldown elapsed."""
        if self._state is CircuitState.OPEN:
            elapsed = time.monotonic() - (self._opened_at or 0.0)
            if elapsed >= self.open_seconds:
                logger.info(
                    "[circuit:%s] cooldown elapsed (%.0fs) → HALF_OPEN",
                    self.source_id,
                    elapsed,
                )
                self._state = CircuitState.HALF_OPEN
        return self._state

    def is_open(self) -> bool:
        """True when the circuit is OPEN (requests must be blocked)."""
        return self.state is CircuitState.OPEN

    def is_available(self) -> bool:
        """True when a request may proceed (CLOSED or HALF_OPEN probe)."""
        s = self.state
        return s is CircuitState.CLOSED or s is CircuitState.HALF_OPEN

    # ── state transitions ────────────────────────────────────────────────────

    def record_success(self) -> None:
        """Call after a successful request.  Resets failures; closes circuit."""
        prev = self._state
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at = None
        if prev is not CircuitState.CLOSED:
            logger.info("[circuit:%s] success → CLOSED", self.source_id)

    def record_failure(self) -> None:
        """Call after a failed request.  May open the circuit."""
        if self._state is CircuitState.HALF_OPEN:
            # Probe failed → back to OPEN; reset the timer
            logger.warning(
                "[circuit:%s] probe failed → OPEN (retry in %.0fs)",
                self.source_id,
                self.open_seconds,
            )
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            return

        if self._state is CircuitState.CLOSED:
            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                logger.warning(
                    "[circuit:%s] %d consecutive failures → OPEN for %.0fs",
                    self.source_id,
                    self._failure_count,
                    self.open_seconds,
                )
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
            else:
                logger.debug(
                    "[circuit:%s] failure %d/%d",
                    self.source_id,
                    self._failure_count,
                    self.failure_threshold,
                )

    # ── convenience ──────────────────────────────────────────────────────────

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"CircuitBreaker(source={self.source_id!r}, "
            f"state={self._state.value}, failures={self._failure_count})"
        )


# ──────────────────────────────────────────────────────────────── rate limiter ──

class RateLimiter:
    """Token-bucket rate limiter (one instance per source).

    Tokens refill continuously at *rate_per_minute / 60* tokens/second.  The
    bucket can hold at most *capacity* tokens (defaults to ``rate_per_minute``).

    Usage::

        rl = RateLimiter("github", rate_per_minute=30)
        if not rl.acquire():
            return []   # over limit – skip request
        # make the request …
    """

    def __init__(
        self,
        source_id: str,
        rate_per_minute: float | None = None,
        capacity: float | None = None,
    ) -> None:
        self.source_id = source_id
        rpm = rate_per_minute or SOURCE_RATE_LIMITS.get(
            source_id, SOURCE_RATE_LIMITS["_default"]
        )
        self.rate_per_second: float = rpm / 60.0
        self.capacity: float = capacity if capacity is not None else rpm

        self._tokens: float = self.capacity
        self._last_refill: float = time.monotonic()
        self._lock = asyncio.Lock()

    # ── internal ─────────────────────────────────────────────────────────────

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self.capacity, self._tokens + elapsed * self.rate_per_second
        )
        self._last_refill = now

    # ── public ───────────────────────────────────────────────────────────────

    def acquire(self, tokens: float = 1.0) -> bool:
        """Attempt to consume *tokens* from the bucket.

        Returns ``True`` if the request is allowed, ``False`` if rate-limited.
        This is a **synchronous** fast-path used outside async contexts.  Inside
        async handlers use :meth:`async_acquire` to avoid lock contention.
        """
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        logger.warning(
            "[rate:%s] request blocked – %.2f tokens available, need %.2f",
            self.source_id,
            self._tokens,
            tokens,
        )
        return False

    async def async_acquire(self, tokens: float = 1.0) -> bool:
        """Async-safe version of :meth:`acquire`."""
        async with self._lock:
            return self.acquire(tokens)

    @property
    def available_tokens(self) -> float:
        self._refill()
        return self._tokens

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"RateLimiter(source={self.source_id!r}, "
            f"rate={self.rate_per_second * 60:.1f}rpm, "
            f"tokens={self._tokens:.2f}/{self.capacity:.2f})"
        )


# ──────────────────────────────────────────────────── per-source singletons ──

_circuit_breakers: dict[str, CircuitBreaker] = {}
_rate_limiters: dict[str, RateLimiter] = {}


def get_circuit_breaker(
    source_id: str,
    failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
    open_seconds: float = DEFAULT_OPEN_SECONDS,
) -> CircuitBreaker:
    """Return (or create) the singleton CircuitBreaker for *source_id*."""
    if source_id not in _circuit_breakers:
        _circuit_breakers[source_id] = CircuitBreaker(
            source_id,
            failure_threshold=failure_threshold,
            open_seconds=open_seconds,
        )
    return _circuit_breakers[source_id]


def get_rate_limiter(
    source_id: str,
    rate_per_minute: float | None = None,
) -> RateLimiter:
    """Return (or create) the singleton RateLimiter for *source_id*."""
    if source_id not in _rate_limiters:
        _rate_limiters[source_id] = RateLimiter(
            source_id, rate_per_minute=rate_per_minute
        )
    return _rate_limiters[source_id]


# ──────────────────────────────────────────── convenience context manager ──

class ResilienceGuard:
    """Combines circuit-breaker checking + rate-limiter checking.

    Use as an async context manager::

        guard = ResilienceGuard("github")
        allowed, reason = await guard.check()
        if not allowed:
            return []   # graceful skip
        try:
            result = await do_request()
            guard.success()
            return result
        except Exception as exc:
            guard.failure()
            raise
    """

    def __init__(self, source_id: str) -> None:
        self.source_id = source_id
        self.cb = get_circuit_breaker(source_id)
        self.rl = get_rate_limiter(source_id)

    async def check(self) -> tuple[bool, str | None]:
        """Return ``(True, None)`` if the request may proceed.

        Returns ``(False, reason_str)`` when blocked.
        """
        if not self.cb.is_available():
            return False, f"circuit open for {self.source_id}"
        if not await self.rl.async_acquire():
            return False, f"rate limit exceeded for {self.source_id}"
        return True, None

    def success(self) -> None:
        self.cb.record_success()

    def failure(self) -> None:
        self.cb.record_failure()
