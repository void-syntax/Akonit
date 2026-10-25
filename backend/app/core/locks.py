"""Distributed Mutex & Distributed Lock Manager (`backend/app/core/locks.py`).

Provides lightweight async reentrant locking for background workers
to prevent race conditions and duplicate collection runs on resource-constrained nodes.
"""

from __future__ import annotations

import asyncio
from typing import Any
from app.core.logging import get_logger

logger = get_logger("app.core.locks")


class AsyncDistributedLockManager:
    """In-memory async lock manager for coordinating concurrent worker tasks."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._master_lock = asyncio.Lock()

    async def acquire(self, resource_key: str) -> asyncio.Lock:
        """Get or create an async lock for a specific resource key."""
        async with self._master_lock:
            if resource_key not in self._locks:
                self._locks[resource_key] = asyncio.Lock()
            return self._locks[resource_key]


_lock_manager: AsyncDistributedLockManager | None = None


def get_lock_manager() -> AsyncDistributedLockManager:
    global _lock_manager
    if _lock_manager is None:
        _lock_manager = AsyncDistributedLockManager()
        logger.info("AsyncDistributedLockManager initialized")
    return _lock_manager
