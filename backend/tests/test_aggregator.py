"""Tests for SlidingWindowAggregator module."""

from __future__ import annotations

import pytest
from app.core.aggregator import SlidingWindowAggregator


def test_sliding_window_aggregator():
    agg = SlidingWindowAggregator(max_samples=10)
    agg.record(10.0)
    agg.record(20.0)
    
    assert agg.average() == 15.0
