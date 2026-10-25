"""Tests for InMemoryEventBus pub/sub broker."""

from __future__ import annotations

import pytest
from app.core.bus import InMemoryEventBus


@pytest.mark.asyncio
async def test_in_memory_event_bus():
    bus = InMemoryEventBus()
    received = []

    async def listener(msg: str) -> None:
        received.append(msg)

    bus.subscribe("signals", listener)
    await bus.publish("signals", "new_ai_signal")

    assert received == ["new_ai_signal"]
