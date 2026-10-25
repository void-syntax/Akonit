"""Lightweight spike anomaly detector using Z-score and EWMA.

Обнаружение всплесков без внешних зависимостей. Чистый Python, O(1) памяти
на один tracked источник/ключевое слово.

Принцип работы:
- EWMA (Exponentially Weighted Moving Average) — сглаженная оценка "нормального" уровня.
- Modified Z-score = (x - median) / (1.4826 * MAD) — устойчивая к выбросам метрика.
- Spike: |z| > threshold (по умолчанию 3.5)

Использование:
    from app.pipeline.detection.anomaly import SpikeDetector
    detector = SpikeDetector.for_source("hackernews")
    is_spike, score = detector.update(current_value)
"""

from __future__ import annotations

import math
from collections import deque
from typing import NamedTuple


class AnomalyResult(NamedTuple):
    is_spike: bool
    z_score: float
    ewma: float
    sample_count: int


class SpikeDetector:
    """Streaming spike detector per named signal source.

    Maintains a sliding window of recent values plus an EWMA baseline.
    Reports a spike when the Z-score exceeds the configured threshold.

    Args:
        alpha:     EWMA smoothing factor (0 < alpha < 1). Higher = less smoothing.
        window:    Number of samples in the rolling window for MAD/median.
        threshold: Z-score threshold to flag as a spike (default 3.5).
    """

    def __init__(
        self,
        alpha: float = 0.15,
        window: int = 60,
        threshold: float = 3.5,
    ) -> None:
        self.alpha = alpha
        self.window = window
        self.threshold = threshold
        self._ewma: float | None = None
        self._samples: deque[float] = deque(maxlen=window)

    def update(self, value: float) -> AnomalyResult:
        """Feed one new observation. Returns anomaly result immediately."""
        # Update EWMA
        if self._ewma is None:
            self._ewma = value
        else:
            self._ewma = self.alpha * value + (1 - self.alpha) * self._ewma

        self._samples.append(value)
        n = len(self._samples)

        if n < 5:
            # Not enough data — never flag a spike
            return AnomalyResult(
                is_spike=False,
                z_score=0.0,
                ewma=self._ewma,
                sample_count=n,
            )

        # Modified Z-score using Median Absolute Deviation (robust vs outliers)
        sorted_vals = sorted(self._samples)
        median = _median(sorted_vals)
        mad = _median([abs(x - median) for x in sorted_vals])

        if mad < 1e-10:
            # Flat signal — any non-zero deviation counts
            z = abs(value - median)
        else:
            z = 0.6745 * (value - median) / mad  # modified z-score

        return AnomalyResult(
            is_spike=abs(z) > self.threshold and value > median,
            z_score=round(z, 3),
            ewma=round(self._ewma, 3),
            sample_count=n,
        )

    def reset(self) -> None:
        self._ewma = None
        self._samples.clear()


def _median(sorted_data: list[float]) -> float:
    n = len(sorted_data)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 0:
        return (sorted_data[mid - 1] + sorted_data[mid]) / 2
    return sorted_data[mid]


# ---------------------------------------------------------------------------
# Per-source registry: one detector per (source_id, metric_key)
# ---------------------------------------------------------------------------

_registry: dict[str, SpikeDetector] = {}


def get_detector(source_id: str, metric_key: str = "activity") -> SpikeDetector:
    """Return the shared SpikeDetector for the given source+metric combination."""
    key = f"{source_id}:{metric_key}"
    if key not in _registry:
        _registry[key] = SpikeDetector()
    return _registry[key]


def check_spike(
    source_id: str,
    value: float,
    metric_key: str = "activity",
) -> AnomalyResult:
    """Feed *value* to the detector for *source_id* and return result."""
    return get_detector(source_id, metric_key).update(value)
