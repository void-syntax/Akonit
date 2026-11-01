"""Tests for Advanced Mathematical & Neural Intelligence Kernel (`backend/tests/test_advanced_kernel.py`)."""

from __future__ import annotations

import pytest
from app.core.advanced_kernel import (
    OnlineStreamingKMeans,
    NystromAttentionEngine,
    KalmanTrendEstimator,
)


def test_online_streaming_kmeans():
    kmeans = OnlineStreamingKMeans(k=4, dimensions=4)
    c1 = kmeans.update([0.1, 0.2, 0.1, 0.2])
    c2 = kmeans.update([0.9, 0.8, 0.9, 0.8])
    c3 = kmeans.update([0.15, 0.25, 0.12, 0.22])
    
    assert c1 == 0
    assert c2 == 1
    assert c3 == 0  # Should cluster with c1


def test_nystrom_attention_engine():
    landmarks = [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
    ]
    query = [0.9, 0.1, 0.0, 0.0]
    score = NystromAttentionEngine.compute_attention_score(query, landmarks)
    assert 0.0 <= score <= 1.0


def test_kalman_trend_estimator():
    kalman = KalmanTrendEstimator()
    v1 = kalman.update(10.0)
    v2 = kalman.update(12.0)
    v3 = kalman.update(15.0)
    assert isinstance(v1, float)
    assert isinstance(v2, float)
    assert isinstance(v3, float)
