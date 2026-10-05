"""Activity metrics: growth, acceleration and normalization.

The key product rule from the brief: POPULAR != RISING. A huge but flat
object must score lower than a small object with sharp acceleration, so every
metric here is relative rather than absolute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

MIN_ACTIVITY = 1.0

# Below this a value is treated as "no measurement yet" rather than as zero.
# Several public feeds (TikTok tag pages, X trends24, Reddit PullPush) legitimately
# expose no count at all, and reporting that as 0 would turn every item into a
# fake 100% jump on its first observation.
NO_MEASUREMENT = 0.0


def now_utc() -> datetime:
    return datetime.now(UTC)


def _is_measured(value: float | None) -> bool:
    """True when the feed actually reported a number for this observation."""
    if value is None:
        return False
    try:
        return float(value) > NO_MEASUREMENT
    except (TypeError, ValueError):
        return False



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
    has_baseline: bool = False
    """True when at least one earlier measurement exists, so growth is meaningful.

    Without a baseline there is nothing to compare against; a signal in that
    state is genuinely new and must not be scored as if it had surged.
    """
    first_measurement: bool = False
    """True when the feed just started reporting a number for this object.

    This is the real "emerging" case: the item existed but had no count before,
    and now it does. It is the one situation where appearing from zero really is
    the signal, and it is tracked separately from ordinary growth.
    """
    points: list[ActivityPoint] = field(default_factory=list)

    @property
    def has_acceleration(self) -> bool:
        return self.acceleration == self.acceleration  # not NaN


def safe_pct(current: float, previous: float) -> float:
    """Percentage growth between two real measurements.

    A previous value of zero means there is no baseline to grow from, so this
    returns 0 rather than pretending the item jumped 100%. The old behaviour made
    every newly discovered signal look like it was surging, which is exactly the
    "everything is RISING" noise the feed had.
    """
    current = max(current, 0.0)
    previous = max(previous, 0.0)
    if previous < MIN_ACTIVITY or current < MIN_ACTIVITY:
        return 0.0
    return ((current - previous) / previous) * 100.0


def weighted_velocity(values: list[float], alpha: float = 0.45) -> float:
    """Exponentially weighted rate of change over a series.

    Comparing only the last two observations is extremely noisy: one bad fetch
    reads as a 200% drop or spike. Weighting recent samples more heavily keeps
    the trend readable, which is what makes BREAKOUT reachable in practice.
    """
    clean = [max(float(v), 0.0) for v in values if v is not None]
    # One sample cannot describe a rate of change. Reporting 100% here is what
    # made every brand-new signal look like it was taking off.
    if len(clean) < 2:
        return 0.0

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

    # A baseline is any earlier observation that actually carried a number.
    measured_before = [p for p in ordered[:-1] if _is_measured(p.activity)]
    metrics.has_baseline = bool(measured_before)

    if measured_before:
        previous = measured_before[-1].activity
    else:
        previous = 0.0
    metrics.previous = previous
    metrics.growth = safe_pct(current, previous)

    # The genuine emerging case: no earlier number, but there is one now.
    metrics.first_measurement = (
        _is_measured(current) and not metrics.has_baseline
    )

    # Smoothed rate of change over the last few windows, far steadier than the
    # raw two-point growth which swings wildly on a single bad fetch. Only
    # measured samples take part, so an unmeasured feed cannot fake momentum.
    series = [p.activity for p in ordered[-6:] if _is_measured(p.activity)]
    metrics.velocity = weighted_velocity(series)

    # Acceleration needs three measured points; without them it stays NaN so the
    # scorer knows the value is unknown rather than zero.
    measured_points = [p.activity for p in ordered if _is_measured(p.activity)]
    if len(measured_points) >= 3:
        prev_prev = measured_points[-3]
        previous_growth = safe_pct(measured_points[-2], prev_prev)
        metrics.acceleration = metrics.growth - previous_growth

    # Persistence: how many consecutive windows kept growing, measured only.
    streak = 0
    series_points = [p.activity for p in ordered if _is_measured(p.activity)]
    for i in range(len(series_points) - 1, 0, -1):
        if series_points[i] > series_points[i - 1]:
            streak += 1
        else:
            break
    metrics.persistence = streak

    first_seen = ordered[0].captured_at
    age = (now - first_seen).total_seconds() / 60
    metrics.age_minutes = max(age, window_minutes)
    metrics.is_new = len(ordered) <= 1
    return metrics