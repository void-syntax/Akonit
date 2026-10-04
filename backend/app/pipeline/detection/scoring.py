"""Signal strength scoring.

Every weight and threshold lives in settings, so the engine is configurable
rather than hardcoded. The scoring deliberately rewards velocity over size:

    strength = growth + acceleration + recency + absolute + persistence
               + cross-source confirmation, each normalized to its weight.

A large flat object scores low. A small object with a sharp spike scores high.
"""

from __future__ import annotations

import math

from app.core.config import settings
from app.pipeline.detection.metrics import GrowthMetrics


def _scale(value: float, ceiling: float) -> float:
    """Map a non-negative value into 0..1 with a soft knee."""
    if value <= 0:
        return 0.0
    return min(value / ceiling, 1.0) ** 0.5


def growth_score(metrics: GrowthMetrics) -> float:
    return _scale(max(metrics.growth, 0.0), 500.0)


def velocity_score(metrics: GrowthMetrics) -> float:
    """Smoothed trend strength. Weighted alongside growth, but capped lower so a
    single huge window cannot dominate: sustained movement beats a one-off spike.
    """
    return _scale(max(metrics.velocity, 0.0), 250.0)


def acceleration_score(metrics: GrowthMetrics) -> float:
    if not metrics.has_acceleration:
        # A brand-new object with growth is inherently accelerating.
        return 0.6 if metrics.growth > 0 else 0.0
    return _scale(max(metrics.acceleration, 0.0), 400.0)


def recency_score(metrics: GrowthMetrics, window_minutes: int = 15) -> float:
    """Younger is better; decays to zero at 48h."""
    hours = metrics.age_minutes / 60
    if hours <= 0:
        return 1.0
    return math.exp(-hours / 12.0)


def absolute_score(metrics: GrowthMetrics) -> float:
    """log-scaled so popularity counts, but never dominates velocity."""
    return min(math.log10(max(metrics.absolute, 0) + 1) / 7.0, 1.0)


def persistence_score(metrics: GrowthMetrics) -> float:
    target = max(settings.detect_persistence_windows, 1)
    return min(metrics.persistence / target, 1.0)


def cross_source_score(count: int) -> float:
    return min(max(count - 1, 0) / 2.0, 1.0)


def staleness_penalty(metrics: GrowthMetrics, window_minutes: int = 15) -> float:
    """Popular but old and not growing must lose points."""
    hours = metrics.age_minutes / 60
    if hours < 6 or metrics.growth > 0:
        return 1.0
    penalty = 1.0 / (1.0 + (hours - 6) / 24.0)
    return max(penalty, 0.25)


def compute_strength(
    metrics: GrowthMetrics,
    *,
    cross_source_count: int = 1,
    window_minutes: int = 15,
) -> float:
    """Return strength in the 0..100 range.

    Weighted sum of the six components (weights come from settings and
    already sum to 100), multiplied by the staleness factor so a big flat
    old object cannot outscore a small sharp one.
    """
    total = (
        growth_score(metrics) * settings.weight_growth
        + velocity_score(metrics) * settings.weight_velocity
        + acceleration_score(metrics) * settings.weight_acceleration
        + recency_score(metrics, window_minutes) * settings.weight_recency
        + absolute_score(metrics) * settings.weight_absolute
        + persistence_score(metrics) * settings.weight_persistence
        + cross_source_score(cross_source_count) * settings.weight_cross_source
    )
    total *= staleness_penalty(metrics, window_minutes)
    return round(min(max(total, 0.0), 100.0), 2)


def strength_components(
    metrics: GrowthMetrics,
    *,
    cross_source_count: int = 1,
    window_minutes: int = 15,
) -> dict[str, float]:
    """Breakdown for the signal detail page."""
    return {
        "growth": round(growth_score(metrics) * settings.weight_growth, 2),
        "velocity": round(velocity_score(metrics) * settings.weight_velocity, 2),
        "acceleration": round(
            acceleration_score(metrics) * settings.weight_acceleration, 2
        ),
        "recency": round(recency_score(metrics, window_minutes) * settings.weight_recency, 2),
        "absolute": round(absolute_score(metrics) * settings.weight_absolute, 2),
        "persistence": round(
            persistence_score(metrics) * settings.weight_persistence, 2
        ),
        "cross_source": round(
            cross_source_score(cross_source_count) * settings.weight_cross_source, 2
        ),
        "staleness_factor": round(staleness_penalty(metrics, window_minutes), 3),
    }