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
    """Return (status, strength) for the current observation."""
    strength = compute_strength(
        metrics, cross_source_count=cross_source_count, window_minutes=window_minutes
    )

    falling = (
        metrics.growth < -20
        or (
            metrics.has_acceleration
            and metrics.acceleration < -30
            and metrics.growth < 0
        )
    )
    drop_ratio = (
        metrics.current / metrics.previous if metrics.previous > 0 else 1.0
    )
    faded = drop_ratio < settings.detect_fading_drop_ratio and metrics.age_minutes > 60

    if faded and strength < settings.detect_rising_strength:
        status = SignalStatus.FADING
    elif strength >= settings.detect_breakout_strength and (
        metrics.growth > 50 or metrics.has_acceleration
    ):
        status = SignalStatus.BREAKOUT
    elif strength >= settings.detect_rising_strength and not falling:
        status = SignalStatus.RISING
    elif strength < settings.detect_min_strength and (
        falling or metrics.age_minutes > 720
    ):
        status = SignalStatus.FADING
    else:
        status = SignalStatus.NEW if metrics.is_new else SignalStatus.RISING

    if status not in ALLOWED.get(previous_status, {status}):
        status = previous_status
    return status, strength


def is_actionable(status: SignalStatus) -> bool:
    """Fading signals stay visible but should not trigger notifications."""
    return status in (SignalStatus.NEW, SignalStatus.RISING, SignalStatus.BREAKOUT)