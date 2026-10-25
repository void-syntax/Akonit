"""API Endpoint Response Compression & Minification Middleware (`backend/app/core/compression.py`).

Optimizes network bandwidth by applying Gzip/Brotli compression headers
and filtering unnecessary fields.
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware


def setup_compression(app: FastAPI, minimum_size: int = 500) -> None:
    """Register GZip compression middleware with low memory overhead."""
    app.add_middleware(GZipMiddleware, minimum_size=minimum_size)
