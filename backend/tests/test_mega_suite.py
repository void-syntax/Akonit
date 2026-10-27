"""Tests for Multi-Vector Intelligence & Optimization Suite."""

from __future__ import annotations

import pytest
from app.core.mega_suite import MinHashLSHPlagiarismDetector, StreamingEMAAnomalizer, get_mega_suite


def test_minhash_plagiarism_detector():
    detector = MinHashLSHPlagiarismDetector(num_hashes=32)
    sig1 = detector.compute_signature("artificial intelligence agent framework release")
    sig2 = detector.compute_signature("artificial intelligence agent framework release")
    sig3 = detector.compute_signature("completely unrelated topic about cooking recipes")

    sim_high = detector.estimate_similarity(sig1, sig2)
    sim_low = detector.estimate_similarity(sig1, sig3)

    assert sim_high == 1.0
    assert sim_low < 0.5


def test_streaming_ema_anomalizer():
    anomalizer = StreamingEMAAnomalizer(alpha=0.3, threshold_multiplier=2.0)
    assert anomalizer.update("github:pytorch", 10.0) is False
    assert anomalizer.update("github:pytorch", 12.0) is False
    # Massive spike
    assert anomalizer.update("github:pytorch", 500.0) is True


def test_mega_suite_singleton():
    suite = get_mega_suite()
    assert "minhash" in suite
    assert "ema" in suite
