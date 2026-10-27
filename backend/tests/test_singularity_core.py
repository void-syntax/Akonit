"""Tests for Cosmic Singularity Intelligence & Multi-Verse Synthesis Core."""

from __future__ import annotations

import pytest
from app.core.singularity_core import StreamingVolatilityIndex, TDigestQuantileTracker, get_singularity_core


def test_streaming_volatility_index():
    vi = StreamingVolatilityIndex(window_size=5)
    assert vi.update(10.0) == 0.0
    vol = vi.update(20.0)
    assert vol > 0.0


def test_tdigest_quantile_tracker():
    tracker = TDigestQuantileTracker()
    for i in range(100):
        tracker.add(float(i))
    
    med = tracker.quantile(0.5)
    assert 40.0 <= med <= 60.0


def test_singularity_core_singleton():
    core = get_singularity_core()
    assert "volatility" in core
    assert "tdigest" in core
