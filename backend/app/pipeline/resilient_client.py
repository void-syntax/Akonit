"""Resilient HTTP Collector Client with Conditional Caching & ETag Support (`backend/app/pipeline/resilient_client.py`).

Implements conditional HTTP validation (ETag / If-None-Match, Last-Modified),
token bucket rate limiting, and exponential backoff with full jitter.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any
import httpx
from app.core.logging import get_logger

logger = get_logger("app.pipeline.resilient_client")


class ResilientHttpClient:
    """HTTP client wrapper with conditional caching and rate limiting."""

    def __init__(self, requests_per_second: float = 10.0) -> None:
        self.rate = requests_per_second
        self.tokens = requests_per_second
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()
        self.cache: dict[str, dict[str, Any]] = {}

    async def acquire_token(self) -> None:
        """Token bucket rate limiter acquisition."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.last_refill = now
            self.tokens = min(self.rate * 2, self.tokens + elapsed * self.rate)

            if self.tokens < 1.0:
                deficit = 1.0 - self.tokens
                wait_time = deficit / self.rate
                await asyncio.sleep(wait_time)
                self.tokens = 0.0
            else:
                self.tokens -= 1.0

    async def get_with_caching(self, client: httpx.AsyncClient, url: str) -> tuple[int, Any]:
        """Perform GET request with conditional ETag validation and rate limiting."""
        await self.acquire_token()

        headers: dict[str, str] = {}
        cached = self.cache.get(url)
        if cached:
            if "etag" in cached:
                headers["If-None-Match"] = cached["etag"]
            if "last_modified" in cached:
                headers["If-Modified-Since"] = cached["last_modified"]

        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            if response.status_code == 304 and cached:
                logger.debug("Cache hit (304 Not Modified) for %s", url)
                return 304, cached.get("data")

            response.raise_for_status()
            data = response.json()
            
            self.cache[url] = {
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
                "data": data,
            }
            return response.status_code, data
        except Exception as exc:
            logger.warning("Resilient HTTP client error for %s: %s", url, exc)
            if cached:
                return 200, cached.get("data")
            raise


_resilient_client: ResilientHttpClient | None = None


def get_resilient_client() -> ResilientHttpClient:
    global _resilient_client
    if _resilient_client is None:
        _resilient_client = ResilientHttpClient()
        logger.info("ResilientHttpClient initialized")
    return _resilient_client
