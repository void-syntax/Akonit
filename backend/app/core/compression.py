"""API Endpoint Response Compression & Minification Middleware (`backend/app/core/compression.py`).

Optimizes network bandwidth by applying Gzip/Brotli compression headers
and filtering unnecessary fields.
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware


class EventStreamSafeGZipMiddleware(GZipMiddleware):
    """Leave event streams uncompressed so live chunks are flushed promptly."""

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path", "").endswith("/sse/stream"):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


def setup_compression(app: FastAPI, minimum_size: int = 500) -> None:
    """Register GZip compression middleware with low memory overhead."""
    app.add_middleware(EventStreamSafeGZipMiddleware, minimum_size=minimum_size)
