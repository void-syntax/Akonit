"""Tests for retry with backoff decorator."""

from __future__ import annotations

import pytest
from app.core.retry import retry_with_backoff


@pytest.mark.asyncio
async def test_retry_success_after_failure():
    attempts = 0

    @retry_with_backoff(retries=3, backoff_in_seconds=0.01)
    async def unstable_task() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("Temporary glitch")
        return "success"

    res = await unstable_task()
    assert res == "success"
    assert attempts == 3
