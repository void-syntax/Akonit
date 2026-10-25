"""Advanced TLS Client session wrapper using curl_cffi for Cloudflare/WAF bypass.
Wraps curl_cffi.requests.AsyncSession to mimic real browser JA3/JA4 & HTTP/2 fingerprints.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger("collector.curl_cffi")

try:
    from curl_cffi.requests import AsyncSession as CurlAsyncSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False


class CurlCffiHttpClient:
    """Drop-in or auxiliary HTTP client using curl_cffi for fingerprint impersonation."""

    def __init__(self, impersonate: str = "chrome120") -> None:
        self.impersonate = impersonate
        self._session: Any | None = None
        self._lock = asyncio.Lock()

    async def _get_session(self) -> Any:
        if not HAS_CURL_CFFI:
            raise RuntimeError("curl_cffi is not installed")
        if self._session is None:
            async with self._lock:
                if self._session is None:
                    self._session = CurlAsyncSession(impersonate=self.impersonate)
        return self._session

    async def get_text(self, url: str, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None, timeout: float = 30.0) -> str:
        session = await self._get_session()
        resp = await session.get(url, headers=headers, params=params, timeout=timeout)
        return resp.text

    async def get_json(self, url: str, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None, timeout: float = 30.0) -> Any:
        session = await self._get_session()
        resp = await session.get(url, headers=headers, params=params, timeout=timeout)
        return resp.json()

    async def aclose(self) -> None:
        if self._session is not None:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None
