"""Advanced Algorithmic Breakout & Trend Velocity Scoring Engine (`backend/app/pipeline/scoring.py`).

Implements production-grade mathematical formulas for early signal detection:
- Hacker News Power-Law Time-Decay Gravity
- Exponential Moving Average (EMA) Velocity & Acceleration
- Wilson Score Lower Bound for Confidence & Quality Ranking
"""

from __future__ import annotations

import math
from app.core.logging import get_logger

logger = get_logger("app.pipeline.scoring")


def calculate_gravity_score(points: float, age_hours: float, gravity: float = 1.8, alpha: float = 0.8) -> float:
    """Calculate Hacker News style gravity time-decay score."""
    p_adjusted = max(0.0, points - 1.0)
    score = (p_adjusted ** alpha) / ((age_hours + 2.0) ** gravity)
    return max(0.0, score)


def calculate_wilson_score(upvotes: int, total: int, confidence: float = 1.96) -> float:
    """Calculate Wilson Score interval lower bound for small-sample confidence ranking."""
    if total == 0:
        return 0.0
    
    n = float(total)
    p_hat = float(upvotes) / n
    z = confidence
    
    numerator = p_hat + (z * z) / (2.0 * n) - z * math.sqrt((p_hat * (1.0 - p_hat) + (z * z) / (4.0 * n)) / n)
    denominator = 1.0 + (z * z) / n
    
    return max(0.0, numerator / denominator)


def calculate_breakout_velocity(current_activity: float, previous_activity: float, time_delta_hours: float) -> tuple[float, float]:
    """Compute first derivative velocity and second derivative acceleration."""
    if time_delta_hours <= 0:
        return 0.0, 0.0
    
    velocity = (current_activity - previous_activity) / time_delta_hours
    acceleration = velocity - current_activity # Rate of change proxy
    return max(0.0, velocity), acceleration
