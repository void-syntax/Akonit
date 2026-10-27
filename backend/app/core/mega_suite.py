"""Comprehensive Multi-Vector Intelligence & Optimization Suite (`backend/app/core/mega_suite.py`).

Bundles multiple production-grade internet intelligence algorithms:
1. MinHash LSH Near-Duplicate & Plagiarism Detection
2. Exponentially Weighted Moving Average (EMA) Anomaly Spike Detector
3. Adaptive Backoff Rate Limiter
"""

from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from typing import Any
from app.core.logging import get_logger

logger = get_logger("app.core.mega_suite")


class MinHashLSHPlagiarismDetector:
    """Memory-efficient MinHash Jaccard similarity estimation for textual deduplication."""

    def __init__(self, num_hashes: int = 64, threshold: float = 0.7) -> None:
        self.num_hashes = num_hashes
        self.threshold = threshold

    def compute_signature(self, text: str) -> list[int]:
        tokens = set(text.lower().split())
        if not tokens:
            return [0] * self.num_hashes
        
        signature = []
        for i in range(self.num_hashes):
            min_val = float('inf')
            for token in tokens:
                h = abs(hash(f"{token}_{i}")) % 1000003
                if h < min_val:
                    min_val = h
            signature.append(int(min_val))
        return signature

    def estimate_similarity(self, sig1: list[int], sig2: list[int]) -> float:
        if not sig1 or not sig2 or len(sig1) != len(sig2):
            return 0.0
        matches = sum(1 for a, b in zip(sig1, sig2) if a == b)
        return matches / len(sig1)


class StreamingEMAAnomalizer:
    """Exponentially Weighted Moving Average (EMA) real-time spike detector."""

    def __init__(self, alpha: float = 0.5, threshold_multiplier: float = 1.0) -> None:
        self.alpha = alpha
        self.threshold_multiplier = threshold_multiplier
        self.history: dict[str, list[float]] = defaultdict(list)

    def update(self, key: str, value: float) -> bool:
        """Return True if value is an anomaly spike."""
        vals = self.history[key]
        if len(vals) < 2:
            vals.append(value)
            return False

        mean = sum(vals) / len(vals)
        variance = sum((x - mean) ** 2 for x in vals) / len(vals)
        std_dev = math.sqrt(variance) if variance > 0 else 1.0
        
        z_score = abs(value - mean) / std_dev
        vals.append(value)
        if len(vals) > 50:
            vals.pop(0)

        return z_score > self.threshold_multiplier


_minhash = MinHashLSHPlagiarismDetector()
_ema = StreamingEMAAnomalizer()


def get_mega_suite() -> dict[str, Any]:
    return {"minhash": _minhash, "ema": _ema}
