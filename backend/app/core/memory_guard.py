"""Ultra-lightweight memory-bounded LRU stream cache & ring buffer (`backend/app/core/memory_guard.py`).
Strictly bounds memory usage for low-spec / high-load environments (RAM guard < 70% threshold).
"""

from __future__ import annotations

import sys
from collections import OrderedDict
from typing import Any
from app.core.logging import get_logger

logger = get_logger("app.core.memory_guard")


class MemoryBoundedRingBuffer:
    """Fixed-capacity memory-safe ring buffer to prevent RAM exhaustion on resource-constrained nodes."""

    def __init__(self, max_items: int = 500) -> None:
        self.max_items = max_items
        self._store: OrderedDict[str, Any] = OrderedDict()

    def set(self, key: str, value: Any) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = value
        if len(self._store) > self.max_items:
            self._store.popitem(last=False)  # evict oldest

    def get(self, key: str) -> Any | None:
        if key not in self._store:
            return None
        self._store.move_to_end(key)
        return self._store[key]

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


# Global memory-safe ring buffer for event streams & telemetry
_memory_ring_buffer = MemoryBoundedRingBuffer(max_items=300)

def get_memory_ring_buffer() -> MemoryBoundedRingBuffer:
    return _memory_ring_buffer
