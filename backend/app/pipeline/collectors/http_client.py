"""Shared HTTP client: retries with exponential backoff, per-host rate limiting."""

from __future__ import annotations

import asyncio
from email.utils import parsedate_to_datetime
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
    "www.producthunt.com": 1.5,
}

_host_last_call: dict[str, float] = {}
_host_locks: dict[str, asyncio.Lock] = {}
_validators: dict[str, dict[str, str]] = {}
_cached_bodies: dict[str, bytes] = {}


def _cache_key(url: str, params: Any = None) -> str:
    request_url = httpx.URL(url)
    if params is not None:
        request_url = request_url.copy_merge_params(params)
    return str(request_url)


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
        self._request_limiter = asyncio.Semaphore(
            max(settings.http_max_concurrency, 1)
        )
        self._client = client or httpx.AsyncClient(
            timeout=settings.fetch_timeout_seconds,
            follow_redirects=True,
            headers=DEFAULT_HEADERS,
            limits=httpx.Limits(
                max_connections=max(settings.http_max_concurrency, 1),
                max_keepalive_connections=max(settings.http_max_concurrency // 2, 1),
            ),
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
        retries: int = 1,
        backoff: float = 1.5,
        raise_on_error: bool = True,
        **kwargs: Any,
    ) -> httpx.Response:
        host = urlparse(url).netloc
        cache_key = _cache_key(url, kwargs.get("params"))
        # Reuse HTTP validators for stable GET resources. A 304 is a normal
        # freshness result, not a collector failure.
        headers = dict(kwargs.pop("headers", {}) or {})
        validator = _validators.get(cache_key, {}) if method.upper() == "GET" else {}
        for name, value in validator.items():
            headers.setdefault(name, value)
        kwargs["headers"] = headers
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            await _pace(host)
            try:
                async with self._request_limiter:
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
                if resp.status_code == 304:
                    return resp
                if method.upper() == "GET":
                    if resp.status_code == 200 and len(resp.content) <= 262_144:
                        if len(_cached_bodies) >= 32 and cache_key not in _cached_bodies:
                            _cached_bodies.pop(next(iter(_cached_bodies)))
                        _cached_bodies[cache_key] = resp.content
                    elif resp.status_code == 200:
                        # A validator without a retained body would turn a 304
                        # into lost data, so large responses stay unconditional.
                        _validators.pop(cache_key, None)
                    fresh = {
                        request_name: resp.headers[response_name]
                        for request_name, response_name in (
                            ("If-None-Match", "etag"),
                            ("If-Modified-Since", "last-modified"),
                        )
                        if response_name in resp.headers
                    }
                    if fresh:
                        if len(_validators) >= 128 and cache_key not in _validators:
                            _validators.pop(next(iter(_validators)))
                        _validators[cache_key] = fresh
                    elif resp.status_code == 200:
                        _validators.pop(cache_key, None)
                if resp.status_code == 429 or resp.status_code == 503:
                    if attempt < retries:
                        delay = _retry_delay(resp, backoff, attempt)
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
        if resp.status_code == 304:
            cached = _cached_bodies.get(_cache_key(url, kw.get("params")))
            if cached is None:
                raise SourceUnavailable(f"not modified without cached body: {url}")
            return cached.decode(resp.encoding or "utf-8", errors="replace")
        return resp.text

    async def get_json(self, url: str, **kw: Any) -> Any:
        resp = await self.get(url, **kw)
        if resp.status_code == 304:
            cached = _cached_bodies.get(_cache_key(url, kw.get("params")))
            if cached is None:
                raise SourceUnavailable(f"not modified without cached body: {url}")
            try:
                import json
                return json.loads(cached)
            except ValueError as exc:
                raise SourceUnavailable(f"cached invalid JSON from {url}: {exc}") from exc
        try:
            return resp.json()
        except ValueError as exc:
            raise SourceUnavailable(f"invalid JSON from {url}: {exc}") from exc


def _retry_delay(response: httpx.Response, backoff: float, attempt: int) -> float:
    """Honor Retry-After without sleeping longer than a bounded worker pause."""
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            return min(max(float(retry_after), 0.0), 60.0)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after).timestamp()
                return min(max(retry_at - time.time(), 0.0), 60.0)
            except (TypeError, ValueError, OverflowError):
                pass
    return min(backoff**attempt + random.uniform(0, 0.6), 30.0)
