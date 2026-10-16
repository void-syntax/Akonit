"""Shared HTTP client: retries with exponential backoff, per-host rate limiting."""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.pipeline.collectors.base import SourceUnavailable

logger = get_logger("collector.http")

DEFAULT_HEADERS = {
    "User-Agent": settings.http_user_agent,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "*/*",
}

# polite per-host pacing (seconds)
_HOST_MIN_INTERVAL: dict[str, float] = {
    "api.github.com": 1.0,
    "huggingface.co": 0.5,
    "api.pullpush.io": 1.0,
    "reddit.com": 2.0,
    "www.reddit.com": 2.0,
    "news.google.com": 1.0,
    "trends.google.com": 1.0,
    "www.tiktok.com": 1.5,
    "www.youtube.com": 1.0,
    "trends24.in": 2.0,
    "api.hackercluster.com": 1.0,
    "hacker-news.firebaseio.com": 0.5,
    "www.producthunt.com": 1.5,
}

_host_last_call: dict[str, float] = {}
_host_locks: dict[str, asyncio.Lock] = {}


def _host_lock(host: str) -> asyncio.Lock:
    return _host_locks.setdefault(host, asyncio.Lock())


async def _pace(host: str) -> None:
    interval = _HOST_MIN_INTERVAL.get(host)
    if not interval:
        return
    async with _host_lock(host):
        last = _host_last_call.get(host, 0.0)
        wait = interval - (time.monotonic() - last)
        if wait > 0:
            await asyncio.sleep(wait)
        _host_last_call[host] = time.monotonic()


class HttpClient:
    """Thin wrapper adding retry/backoff and rate-limit pacing to httpx."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=settings.fetch_timeout_seconds,
            follow_redirects=True,
            headers=DEFAULT_HEADERS,
        )
        self._owned = client is None

    async def aclose(self) -> None:
        if self._owned:
            await self._client.aclose()

    async def request(
        self,
        method: str,
        url: str,
        *,
        retries: int = 3,
        backoff: float = 1.5,
        raise_on_error: bool = True,
        **kwargs: Any,
    ) -> httpx.Response:
        host = urlparse(url).netloc
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            await _pace(host)
            try:
                resp = await self._client.request(method, url, **kwargs)
            except Exception as exc:  # network error
                last_exc = exc
                resp = None
                if attempt >= retries:
                    if raise_on_error:
                        raise SourceUnavailable(
                            f"failed after {retries + 1} attempts: {url} ({last_exc})"
                        )
                    return None
                delay = backoff ** attempt + random.uniform(0, 0.6)
                await asyncio.sleep(delay)
                continue

            if resp is not None:
                if resp.status_code == 429 or resp.status_code == 503:
                    if attempt < retries:
                        delay = backoff**attempt + random.uniform(0, 0.6)
                        logger.warning(
                            "rate limited (%s) on %s, retry in %.1fs",
                            resp.status_code,
                            host,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                if resp.status_code >= 500 and attempt < retries:
                    delay = backoff**attempt + random.uniform(0, 0.6)
                    await asyncio.sleep(delay)
                    continue
                if resp.status_code >= 400:
                    if raise_on_error:
                        raise SourceUnavailable(
                            f"HTTP {resp.status_code} from {url}"
                        )
                    return resp

            return resp  # type: ignore[return-value]

        if raise_on_error:
            raise SourceUnavailable(
                f"failed after {retries + 1} attempts: {url} ({last_exc})"
            )
        return None

    async def get(self, url: str, **kw: Any) -> httpx.Response:
        return await self.request("GET", url, **kw)

    async def get_text(self, url: str, **kw: Any) -> str:
        resp = await self.get(url, **kw)
        return resp.text

    async def get_json(self, url: str, **kw: Any) -> Any:
        resp = await self.get(url, **kw)
        try:
            return resp.json()
        except ValueError as exc:
            raise SourceUnavailable(f"invalid JSON from {url}: {exc}") from exc