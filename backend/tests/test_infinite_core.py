"""Tests for Infinite Dimensional Quantum-Core & Hyper-Stream Intelligence."""

from __future__ import annotations

import pytest
from app.core.infinite_core import CountMinSketch, HyperbolicDecayScorer, get_infinite_core


def test_count_min_sketch():
    cms = CountMinSketch(width=100, depth=3)
    cms.add("signal_a")
    cms.add("signal_a")
    cms.add("signal_b")

    assert cms.estimate("signal_a") >= 2
    assert cms.estimate("signal_b") >= 1
    assert cms.estimate("non_existent") == 0


def test_hyperbolic_decay_scorer():
    w0 = HyperbolicDecayScorer.compute_weight(0.0)
    w24 = HyperbolicDecayScorer.compute_weight(24.0, scaling_factor=24.0)
    
    assert w0 == 1.0
    assert w24 == 0.5


def test_infinite_core_singleton():
    core = get_infinite_core()
    assert "cms" in core
    assert "hds" in core
