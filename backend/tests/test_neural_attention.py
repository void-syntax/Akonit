"""Tests for Quantum-Resilient Neural Semantic Similarity & Attention Matrix Engine."""

from __future__ import annotations

import pytest
from app.core.neural_attention import LightweightSelfAttentionScorer, get_neural_attention


def test_lightweight_self_attention():
    query = [1.0, 0.0, 1.0]
    keys = [
        [1.0, 0.0, 1.0],
        [0.0, 1.0, 0.0],
        [-1.0, -1.0, 0.0]
    ]

    weights = LightweightSelfAttentionScorer.compute_attention(query, keys)
    assert len(weights) == 3
    assert abs(sum(weights) - 1.0) < 1e-5
    assert weights[0] > weights[2]


def test_neural_attention_singleton():
    engine = get_neural_attention()
    assert "attention" in engine
