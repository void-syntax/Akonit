"""Production-grade high-performance compression and optimization middleware
using Starlette-Compress / Brotli / GZip fallback for FastAPI.
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware

try:
    from starlette_compress import CompressMiddleware
    HAS_STARLETTE_COMPRESS = True
except ImportError:
    HAS_STARLETTE_COMPRESS = False


def setup_compression(app: FastAPI, minimum_size: int = 500) -> None:
    """Configure modern compression (Brotli/Zstd/Gzip) on FastAPI app."""
    if HAS_STARLETTE_COMPRESS:
        app.add_middleware(
            CompressMiddleware,
            minimum_size=minimum_size,
            brotli_quality=6,
            gzip_level=6,
        )
    else:
        app.add_middleware(
            GZipMiddleware,
            minimum_size=minimum_size,
        )
