"""Tests for advanced scoring and breakout velocity algorithms."""

from __future__ import annotations

import pytest
from app.pipeline.scoring import (
    calculate_gravity_score,
    calculate_wilson_score,
    calculate_breakout_velocity,
)


def test_gravity_score():
    score_new = calculate_gravity_score(points=50.0, age_hours=0.5)
    score_old = calculate_gravity_score(points=50.0, age_hours=24.0)
    assert score_new > score_old


def test_wilson_score():
    # 9/10 vs 900/1000 -> Wilson score penalizes low sample size
    w_small = calculate_wilson_score(9, 10)
    w_large = calculate_wilson_score(900, 1000)
    assert w_large > w_small


def test_breakout_velocity():
    vel, acc = calculate_breakout_velocity(current_activity=100.0, previous_activity=50.0, time_delta_hours=1.0)
    assert vel == 50.0
    assert isinstance(acc, float)
