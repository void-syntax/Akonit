"""API Response Caching & ETag Validation Middleware (`backend/app/core/etag.py`).

Generates cryptographic ETags for API responses to enable client-side
conditional caching and reduce bandwidth usage.
"""

from __future__ import annotations

import hashlib
from app.core.logging import get_logger

logger = get_logger("app.core.etag")


def generate_etag(content: bytes) -> str:
    """Generate SHA-256 ETag hash for response content."""
    digest = hashlib.sha256(content).hexdigest()[:16]
    return f'"{digest}"'
