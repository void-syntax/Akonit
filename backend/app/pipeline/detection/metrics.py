"""Activity metrics: growth, acceleration and normalization.

The key product rule from the brief: POPULAR != RISING. A huge but flat
object must score lower than a small object with sharp acceleration, so every
metric here is relative rather than absolute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

MIN_ACTIVITY = 1.0


def now_utc() -> datetime:
    return datetime.now(UTC)


@dataclass
class ActivityPoint:
    captured_at: datetime
    activity: float


@dataclass
class GrowthMetrics:
    growth: float = 0.0
    """Percentage change vs the previous observation window."""
    acceleration: float = float("nan")
    """Change of growth itself (second derivative). NaN when unknown."""
    velocity: float = 0.0
    """Smoothed rate of change across the whole series. This is what identifies
    a trend taking off, instead of a single noisy window."""
    absolute: float = 0.0
    persistence: int = 0
    """Consecutive windows with increasing activity."""
    age_minutes: float = 0.0
    rank: int | None = None
    current: float = 0.0
    previous: float = 0.0
    is_new: bool = True
    points: list[ActivityPoint] = field(default_factory=list)

    @property
    def has_acceleration(self) -> bool:
        return self.acceleration == self.acceleration  # not NaN


def safe_pct(current: float, previous: float) -> float:
    """Percentage growth; an object appearing from zero counts as 100%."""
    current = max(current, 0.0)
    previous = max(previous, 0.0)
    if previous < MIN_ACTIVITY:
        return 100.0 if current >= MIN_ACTIVITY else 0.0
    return ((current - previous) / previous) * 100.0


def weighted_velocity(values: list[float], alpha: float = 0.45) -> float:
    """Exponentially weighted rate of change over a series.

    Comparing only the last two observations is extremely noisy: one bad fetch
    reads as a 200% drop or spike. Weighting recent samples more heavily keeps
    the trend readable, which is what makes BREAKOUT reachable in practice.
    """
    clean = [max(float(v), 0.0) for v in values if v is not None]
    if len(clean) < 2:
        return 100.0 if clean and clean[-1] >= MIN_ACTIVITY else 0.0

    velocity = 0.0
    weight_sum = 0.0
    for index in range(1, len(clean)):
        step = safe_pct(clean[index], clean[index - 1])
        # Most recent sample carries the most weight.
        weight = alpha ** (len(clean) - 1 - index)
        velocity += step * weight
        weight_sum += weight

    return velocity / weight_sum if weight_sum else 0.0


def compute_growth_acceleration(
    history: list[ActivityPoint],
    *,
    now: datetime | None = None,
    rank: int | None = None,
    window_minutes: int = 15,
) -> GrowthMetrics:
    """Derive growth / acceleration / persistence from the snapshot history."""
    now = now or now_utc()
    ordered = sorted(history, key=lambda p: p.captured_at)
    metrics = GrowthMetrics(rank=rank, points=ordered)

    if not ordered:
        return metrics

    current = ordered[-1].activity
    metrics.current = current
    metrics.absolute = current

    if len(ordered) == 1:
        previous = 0.0
    else:
        previous = ordered[-2].activity
    metrics.previous = previous
    metrics.growth = safe_pct(current, previous)

    # Smoothed rate of change over the last few windows, far steadier than the
    # raw two-point growth which swings wildly on a single bad fetch.
    series = [p.activity for p in ordered[-6:]]
    metrics.velocity = weighted_velocity(series)

    if len(ordered) >= 3:
        prev_prev = ordered[-3].activity
        previous_growth = safe_pct(previous, prev_prev)
        metrics.acceleration = metrics.growth - previous_growth

    # Persistence: how many consecutive windows kept growing.
    streak = 0
    for i in range(len(ordered) - 1, 0, -1):
        if ordered[i].activity > ordered[i - 1].activity:
            streak += 1
        else:
            break
    metrics.persistence = streak

    first_seen = ordered[0].captured_at
    age = (now - first_seen).total_seconds() / 60
    metrics.age_minutes = max(age, window_minutes)
    metrics.is_new = len(ordered) <= 1
    return metrics