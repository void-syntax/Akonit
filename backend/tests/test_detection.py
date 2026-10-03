"""Unit tests for the detection engine (scoring, lifecycle, metrics)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.models.enums import SignalStatus
from app.pipeline.detection.lifecycle import classify, is_actionable
from app.pipeline.detection.metrics import (
    ActivityPoint,
    compute_growth_acceleration,
    safe_pct,
)
from app.pipeline.detection.scoring import compute_strength

NOW = datetime.now(UTC)


def points(values: list[float], minutes: int = 15) -> list:
    """Build a chronological series: the LAST value is the newest observation."""
    from app.pipeline.detection.metrics import ActivityPoint

    return [
        ActivityPoint(
            captured_at=NOW - timedelta(minutes=minutes * (len(values) - 1 - i)),
            activity=value,
        )
        for i, value in enumerate(values)
    ]


class TestMetrics:
    def test_growth_from_zero_is_full(self):
        assert safe_pct(100, 0) == 100.0
        assert safe_pct(0, 0) == 0.0

    def test_growth_percentage(self):
        assert safe_pct(200, 100) == 100.0
        assert safe_pct(50, 100) == -50.0

    def test_acceleration_needs_three_points(self):
        """Acceleration is the change of growth, so it needs a third point."""
        two = compute_growth_acceleration(points([100, 200]), now=NOW)
        assert not two.has_acceleration

        three = compute_growth_acceleration(points([100, 200, 400]), now=NOW)
        assert three.has_acceleration
        # growth: 100->200 = +100%, 200->400 = +100% => acceleration 0
        assert three.acceleration == 0.0

        accelerating = compute_growth_acceleration(
            points([100, 200, 800]), now=NOW
        )
        # growth: +100% then +300% => acceleration +200
        assert accelerating.acceleration == 200.0

    def test_persistence_counts_growing_windows(self):
        metrics = compute_growth_acceleration(points([10, 20, 40, 80]), now=NOW)
        assert metrics.persistence == 3


class TestScoring:
    def test_popular_but_flat_scores_lower_than_sharp_rise(self):
        """The core product rule: POPULAR != RISING."""
        flat = compute_growth_acceleration(points([50000, 50000, 50000]), now=NOW)
        sharp = compute_growth_acceleration(
            points([10, 40, 400, 1600]), now=NOW
        )

        flat_strength = compute_strength(flat)
        sharp_strength = compute_strength(sharp)

        assert sharp_strength > flat_strength, (
            f"sharp={sharp_strength} should beat flat={flat_strength}"
        )

    def test_old_flat_object_is_penalised(self):
        old_points = [
            ActivityPoint(
                captured_at=NOW - timedelta(hours=72), activity=100000
            ),
            ActivityPoint(
                captured_at=NOW - timedelta(hours=48), activity=100000
            ),
            ActivityPoint(
                captured_at=NOW - timedelta(hours=24), activity=100000
            ),
        ]
        old_flat = compute_growth_acceleration(old_points, now=NOW)
        fresh_sharp = compute_growth_acceleration(
            points([10, 50, 500, 3000]), now=NOW
        )
        assert compute_strength(fresh_sharp) > compute_strength(old_flat)

    def test_strength_within_bounds(self):
        for values in ([0], [1, 1], [1, 1000], [5, 5, 5, 5]):
            metrics = compute_growth_acceleration(points(values), now=NOW)
            strength = compute_strength(metrics)
            assert 0.0 <= strength <= 100.0


class TestLifecycle:
    def test_status_transitions_are_valid(self):
        for previous in SignalStatus:
            for values in ([1], [1, 2], [1, 10, 100], [100, 50, 10]):
                metrics = compute_growth_acceleration(points(values), now=NOW)
                status, strength = classify(metrics, previous_status=previous)
                assert status in SignalStatus
                assert 0.0 <= strength <= 100.0

    def test_breakout_requires_high_strength(self):
        metrics = compute_growth_acceleration(
            points([10, 60, 500, 5000]), now=NOW
        )
        status, strength = classify(metrics)
        if strength >= settings.detect_breakout_strength:
            assert status == SignalStatus.BREAKOUT

    def test_fading_is_not_actionable(self):
        assert not is_actionable(SignalStatus.FADING)
        assert is_actionable(SignalStatus.BREAKOUT)
        assert is_actionable(SignalStatus.RISING)