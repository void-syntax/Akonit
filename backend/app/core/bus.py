"""In-Memory Distributed Event Bus & PubSub Broker (`backend/app/core/bus.py`).

Provides lightning-fast in-process pub/sub messaging for real-time SSE stream updates
and signal dispatching without Redis dependency overhead.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine
from app.core.logging import get_logger

logger = get_logger("app.core.bus")


class InMemoryEventBus:
    """Async pub/sub event bus for real-time signal broadcasting."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[Any], Coroutine[Any, Any, None]]]] = {}

    def subscribe(self, topic: str, callback: Callable[[Any], Coroutine[Any, Any, None]]) -> None:
        """Subscribe an async callback to a topic."""
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(callback)

    async def publish(self, topic: str, message: Any) -> None:
        """Publish a message to all subscribers of a topic."""
        if topic not in self._subscribers:
            return
        await asyncio.gather(
            *(cb(message) for cb in self._subscribers[topic]),
            return_exceptions=True,
        )


_bus: InMemoryEventBus | None = None


def get_event_bus() -> InMemoryEventBus:
    global _bus
    if _bus is None:
        _bus = InMemoryEventBus()
        logger.info("InMemoryEventBus initialized")
    return _bus
