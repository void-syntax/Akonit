"""Tests for Hyper-Optimized Multi-Core Intelligence Engine."""

from __future__ import annotations

import pytest
from app.core.hyper_engine import HyperIntelligenceRingBuffer, HyperScoringEngine, get_hyper_engine


def test_hyper_ring_buffer():
    buf = HyperIntelligenceRingBuffer(max_items=10)
    buf.append({"id": "1", "title": "Test Signal"})
    assert buf.size == 1
    recent = buf.query_recent(60.0)
    assert len(recent) == 1


def test_hyper_scoring_engine():
    score = HyperScoringEngine.compute_hyper_score(points=100.0, velocity=10.0, age_hours=1.0)
    assert score > 0.0


def test_hyper_engine_singleton():
    engine = get_hyper_engine()
    assert "ring_buffer" in engine
    assert "scoring" in engine
