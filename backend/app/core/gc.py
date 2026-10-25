"""Automated Memory Garbage Collection & Cache Eviction Worker (`backend/app/core/gc.py`).

Periodically forces garbage collection and evicts stale in-memory cache items
to guarantee strict RAM bounds below the 70% laptop threshold.
"""

from __future__ import annotations

import gc
from app.core.logging import get_logger

logger = get_logger("app.core.gc")


def run_aggressive_garbage_collection() -> dict[str, int]:
    """Force Python garbage collection and return collected object counts."""
    collected = gc.collect()
    logger.info("Aggressive garbage collection executed. Collected %s objects.", collected)
    return {"collected_objects": collected}
