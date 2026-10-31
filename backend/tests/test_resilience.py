from __future__ import annotations

import time
import pytest

from app.pipeline.resilience import (
    CircuitBreaker,
    CircuitState,
    RateLimiter,
    get_circuit_breaker,
)
from app.pipeline.collectors.base import FetchContext, FetchResult, Strategy
from app.pipeline.collectors.registry import (
    run_strategy_cascade,
    SourceAdapter,
    register_source,
)
from app.models.enums import SourceType


def test_circuit_breaker_opens_after_three_failures():
    cb = CircuitBreaker("test_source_cb", failure_threshold=3, open_seconds=10.0)
    assert cb.state is CircuitState.CLOSED
    assert not cb.is_open()

    # 1 failure
    cb.record_failure()
    assert cb.state is CircuitState.CLOSED

    # 2 failures
    cb.record_failure()
    assert cb.state is CircuitState.CLOSED

    # 3 failures -> opens circuit
    cb.record_failure()
    assert cb.state is CircuitState.OPEN
    assert cb.is_open()
    assert not cb.is_available()


def test_circuit_breaker_half_opens_after_cooldown():
    # Very short cooldown for testing
    cb = CircuitBreaker("test_source_cooldown", failure_threshold=1, open_seconds=0.01)
    assert cb.state is CircuitState.CLOSED

    cb.record_failure()
    assert cb.state is CircuitState.OPEN
    assert cb.is_open()

    # Wait for cooldown
    time.sleep(0.04)

    # Should transition to HALF_OPEN on state check
    assert cb.state is CircuitState.HALF_OPEN
    assert cb.is_available()  # Probe allowed

    # Success should close it again
    cb.record_success()
    assert cb.state is CircuitState.CLOSED


def test_rate_limiter_blocks_excess_requests():
    # 60 req per min = 1 req per sec. Capacity = 2.
    rl = RateLimiter("test_source_rl", rate_per_minute=60.0, capacity=2.0)

    # Consume 2 tokens
    assert rl.acquire(1.0) is True
    assert rl.acquire(1.0) is True

    # 3rd request should fail since bucket is empty
    assert rl.acquire(1.0) is False


@pytest.mark.asyncio
async def test_rate_limiter_async_acquire():
    rl = RateLimiter("test_source_async_rl", rate_per_minute=120.0, capacity=1.0)
    assert await rl.async_acquire(1.0) is True
    assert await rl.async_acquire(1.0) is False


class MockFailingStrategy(Strategy):
    name = "fail_strategy"

    async def fetch(self, client, ctx):
        raise RuntimeError("network error")


@register_source
class MockFailingAdapter(SourceAdapter):
    source_id = "test_failing_adapter"
    name = "Test Failing Adapter"
    type = SourceType.NEWS
    strategies = [MockFailingStrategy()]

    async def fetch(self, ctx: FetchContext, client: any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)


@pytest.mark.asyncio
async def test_adapters_return_empty_list_gracefully_when_circuit_open():
    adapter = get_adapter_local("test_failing_adapter")
    cb = get_circuit_breaker(
        "test_failing_adapter", failure_threshold=1, open_seconds=60.0
    )

    # Force circuit open
    cb._state = CircuitState.OPEN
    cb._opened_at = time.monotonic()

    ctx = FetchContext(limit=10)
    result = await run_strategy_cascade(adapter, ctx, None)

    assert result.ok is True
    assert result.events == []
    assert "circuit" in (result.notes or "").lower()


def get_adapter_local(source_id: str):
    from app.pipeline.collectors.registry import get_adapter

    return get_adapter(source_id)
