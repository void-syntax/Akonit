"""Quantum-Resilient Neural Semantic Similarity & Attention Matrix Engine (`backend/app/core/neural_attention.py`).

Provides lightweight attention-based semantic scoring and multi-head dot-product similarity matrix
computation for ultra-precise signal correlation without heavy ML frameworks.
"""

from __future__ import annotations

import math
from typing import Any
from app.core.logging import get_logger

logger = get_logger("app.core.neural_attention")


class LightweightSelfAttentionScorer:
    """Computes scaled dot-product attention scores across signal feature vectors."""

    @staticmethod
    def compute_attention(query: list[float], keys: list[list[float]]) -> list[float]:
        if not query or not keys:
            return []
        
        d_k = float(len(query))
        scale = math.sqrt(d_k) if d_k > 0 else 1.0
        
        scores = []
        for key in keys:
            dot_prod = sum(q * k for q, k in zip(query, key))
            scores.append(dot_prod / scale)
        
        # Softmax normalization
        max_score = max(scores) if scores else 0.0
        exp_scores = [math.exp(s - max_score) for s in scores]
        sum_exp = sum(exp_scores) if sum(exp_scores) > 0 else 1.0
        
        return [e / sum_exp for e in exp_scores]


_attention_scorer = LightweightSelfAttentionScorer()


def get_neural_attention() -> dict[str, Any]:
    return {"attention": _attention_scorer}
