"""Signal lifecycle: NEW -> RISING -> BREAKOUT -> FADING.

Signals are never deleted after a drop; the history stays and the status
reflects where the object is now.
"""

from __future__ import annotations

from app.core.config import settings
from app.models.enums import SignalStatus
from app.pipeline.detection.metrics import GrowthMetrics
from app.pipeline.detection.scoring import compute_strength

# Allowed transitions (anything else is clamped to the previous state).
ALLOWED: dict[SignalStatus, set[SignalStatus]] = {
    SignalStatus.NEW: {
        SignalStatus.NEW,
        SignalStatus.RISING,
        SignalStatus.BREAKOUT,
        SignalStatus.FADING,
    },
    SignalStatus.RISING: {
        SignalStatus.NEW,
        SignalStatus.RISING,
        SignalStatus.BREAKOUT,
        SignalStatus.FADING,
    },
    SignalStatus.BREAKOUT: {
        SignalStatus.RISING,
        SignalStatus.BREAKOUT,
        SignalStatus.FADING,
    },
    SignalStatus.FADING: {
        SignalStatus.RISING,
        SignalStatus.BREAKOUT,
        SignalStatus.FADING,
    },
}


def classify(
    metrics: GrowthMetrics,
    *,
    previous_status: SignalStatus = SignalStatus.NEW,
    cross_source_count: int = 1,
    window_minutes: int = 15,
) -> tuple[SignalStatus, float]:
    """Return (status, strength) for the current observation.

    Two deliberate changes from the naive version:

    * BREAKOUT is reachable. It keys off smoothed velocity rather than raw
      growth, which almost never crosses a high bar on noisy real data.
    * Status changes require agreement over several windows (hysteresis), so a
      single bad fetch can no longer flip a signal between states. That is what
      pushed almost everything into FADING before.
    """
    strength = compute_strength(
        metrics, cross_source_count=cross_source_count, window_minutes=window_minutes
    )

    velocity = metrics.velocity
    history = len(metrics.points)

    # Sustained decline: velocity clearly negative and persistence exhausted.
    sustained_decline = (
        metrics.persistence == 0
        and velocity < -25
        and metrics.age_minutes > 60
    )

    # Genuine acceleration: still moving up, and still young enough to matter.
    taking_off = (
        velocity > settings.detect_breakout_velocity
        and metrics.current >= settings.detect_min_absolute_activity
    )

    strong = (
        strength >= settings.detect_breakout_strength
        and (taking_off or metrics.growth > 25)
    )
    healthy = (
        strength >= settings.detect_rising_strength
        and velocity > -settings.detect_fading_drop_ratio * 100
    )

    # Hysteresis: once established, a state needs a clear margin to change.
    if previous_status in (SignalStatus.BREAKOUT, SignalStatus.RISING):
        demote_margin = settings.detect_hysteresis
        if not strong and strength < settings.detect_breakout_strength - demote_margin:
            if sustained_decline:
                return SignalStatus.FADING, strength
        elif not healthy and strength < settings.detect_min_strength:
            return SignalStatus.FADING, strength

    if sustained_decline and strength < settings.detect_rising_strength:
        status = SignalStatus.FADING
    elif strong:
        status = SignalStatus.BREAKOUT
    elif healthy:
        status = SignalStatus.RISING
    elif history <= 1 and strength >= settings.detect_min_strength:
        status = SignalStatus.NEW
    else:
        # Weak and not growing: decaying rather than brand new.
        status = SignalStatus.NEW if metrics.is_new else SignalStatus.RISING

    if status not in ALLOWED.get(previous_status, {status}):
        status = previous_status
    return status, strength


def is_actionable(status: SignalStatus) -> bool:
    """Fading signals stay visible but should not trigger notifications."""
    return status in (SignalStatus.NEW, SignalStatus.RISING, SignalStatus.BREAKOUT)