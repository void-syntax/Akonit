"""Tests for Supreme Infinite Intelligence & Autonomous Neural Synthesis Kernel."""

from __future__ import annotations

import pytest
from app.core.supreme_kernel import OnlineKalmanTrendTracker, InformationEntropyNoveltyFilter, get_supreme_kernel


def test_online_kalman_trend_tracker():
    tracker = OnlineKalmanTrendTracker()
    smoothed1 = tracker.update(10.0)
    smoothed2 = tracker.update(12.0)
    
    assert isinstance(smoothed1, float)
    assert isinstance(smoothed2, float)


def test_information_entropy_novelty_filter():
    freqs = {"ai": 10, "agent": 5, "quantum": 1}
    total = 16
    
    surprise_common = InformationEntropyNoveltyFilter.compute_surprise(freqs, total, "ai")
    surprise_rare = InformationEntropyNoveltyFilter.compute_surprise(freqs, total, "quantum")
    
    assert surprise_rare > surprise_common


def test_supreme_kernel_singleton():
    kernel = get_supreme_kernel()
    assert "kalman" in kernel
    assert "entropy" in kernel
