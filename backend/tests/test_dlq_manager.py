"""Tests for DeadLetterQueue retry manager."""

from __future__ import annotations

import pytest
from app.pipeline.dlq_manager import DeadLetterQueue


@pytest.mark.asyncio
async def test_dlq_push_and_retry():
    dlq = DeadLetterQueue(maxsize=10)
    dlq.push({"data": "test_payload"}, "network_timeout")
    assert dlq.size == 1

    async def mock_handler(event: dict) -> bool:
        return event["data"] == "test_payload"

    retried = await dlq.retry_loop(mock_handler, max_attempts=3)
    assert retried == 1
    assert dlq.size == 0
