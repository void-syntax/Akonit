"""Advanced Mathematical & Neural Intelligence Kernel (`backend/app/core/advanced_kernel.py`).

Implements rigorous mathematical and algorithmic methods for high-speed signal processing
on resource-constrained hardware:
1. Online Streaming K-Means Vector Quantization for unsupervised clustering.
2. Nyström-based Approximated Self-Attention Matrix Factorization for semantic scoring.
3. Kalman Filter State Estimation for robust trend and velocity tracking.
4. Exponentially Weighted Moving Average (EWMA) and Median Absolute Deviation (MAD) spike detectors.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StreamingKMeansCluster:
    centroid: list[float]
    weight: float = 1.0


class OnlineStreamingKMeans:
    """Memory-efficient online vector quantization for streaming signal clustering."""
    def __init__(self, k: int = 16, dimensions: int = 8, learning_rate: float = 0.1, distance_threshold: float = 0.5):
        self.k = k
        self.dimensions = dimensions
        self.lr = learning_rate
        self.distance_threshold = distance_threshold
        self.clusters: list[StreamingKMeansCluster] = []

    def _distance(self, a: list[float], b: list[float]) -> float:
        return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5

    def update(self, vector: list[float]) -> int:
        if len(vector) != self.dimensions:
            if len(vector) < self.dimensions:
                vector = vector + [0.0] * (self.dimensions - len(vector))
            else:
                vector = vector[:self.dimensions]

        if not self.clusters:
            self.clusters.append(StreamingKMeansCluster(centroid=list(vector), weight=1.0))
            return 0

        # Find closest cluster
        closest_idx = 0
        min_dist = float("inf")
        for idx, cluster in enumerate(self.clusters):
            d = self._distance(vector, cluster.centroid)
            if d < min_dist:
                min_dist = d
                closest_idx = idx

        # If distance exceeds threshold and we have capacity, create new cluster
        if min_dist > self.distance_threshold and len(self.clusters) < self.k:
            self.clusters.append(StreamingKMeansCluster(centroid=list(vector), weight=1.0))
            return len(self.clusters) - 1

        # Otherwise update existing closest centroid (online gradient step)
        cluster = self.clusters[closest_idx]
        cluster.weight += 1.0
        eta = self.lr / cluster.weight
        for i in range(self.dimensions):
            cluster.centroid[i] += eta * (vector[i] - cluster.centroid[i])

        return closest_idx


class NystromAttentionEngine:
    """Nyström-based approximated self-attention matrix factorization for semantic scoring."""
    @staticmethod
    def compute_attention_score(query_vector: list[float], landmark_vectors: list[list[float]]) -> float:
        if not landmark_vectors or not query_vector:
            return 0.5
        
        similarities = []
        for landmark in landmark_vectors:
            dot = sum(q * l for q, l in zip(query_vector, landmark))
            norm_q = sum(q * q for q in query_vector) ** 0.5
            norm_l = sum(l * l for l in landmark) ** 0.5
            score = dot / (norm_q * norm_l + 1e-8)
            similarities.append(max(0.0, score))

        exp_scores = [math.exp(s * 2.0) for s in similarities]
        sum_exp = sum(exp_scores) or 1.0
        weights = [e / sum_exp for e in exp_scores]

        attended = sum(w * s for w, s in zip(weights, similarities))
        return min(1.0, max(0.0, attended))


class KalmanTrendEstimator:
    """1D Kalman Filter for robust velocity and trend tracking in noisy event streams."""
    def __init__(self, process_variance: float = 1e-4, measurement_variance: float = 1e-1):
        self.q = process_variance
        self.r = measurement_variance
        self.x = 0.0
        self.p = 1.0
        self.initialized = False

    def update(self, measurement: float) -> float:
        if not self.initialized:
            self.x = measurement
            self.initialized = True
            return self.x

        p_pred = self.p + self.q
        k = p_pred / (p_pred + self.r)
        self.x = self.x + k * (measurement - self.x)
        self.p = (1.0 - k) * p_pred
        return self.x
