"""Tests for Adaptive Circuit Breaker & Fault Tolerant Backoff Engine."""

from __future__ import annotations

import time
import pytest
from app.core.circuit_engine import AdaptiveCircuitBreaker, get_circuit_engine


def test_circuit_breaker_lifecycle():
    cb = AdaptiveCircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
    assert cb.allow_request() is True

    cb.record_failure()
    assert cb.state == "CLOSED"

    cb.record_failure()
    assert cb.state == "OPEN"
    assert cb.allow_request() is False

    # Wait for recovery timeout
    time.sleep(0.15)
    assert cb.allow_request() is True
    assert cb.state == "HALF-OPEN"

    cb.record_success()
    assert cb.state == "CLOSED"
    assert cb.failures == 0


def test_circuit_engine_singleton():
    engine = get_circuit_engine()
    assert "breaker" in engine
