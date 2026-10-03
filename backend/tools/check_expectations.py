"""Print the real values so test expectations can match actual behaviour."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.pipeline.detection.metrics import (
    ActivityPoint,
    compute_growth_acceleration,
)
from app.pipeline.normalization.normalizer import (
    normalize_text,
    similarity,
    simhash,
)

NOW = datetime.now(UTC)


def series(values: list[float]) -> list[ActivityPoint]:
    return [
        ActivityPoint(
            captured_at=NOW - timedelta(minutes=15 * i), activity=value
        )
        for i, value in enumerate(values)
    ]


def main() -> None:
    print("normalize_text('  K-Beauty!!!  ') ->", repr(normalize_text("  K-Beauty!!!  ")))

    a = simhash("new viral makeup trend in korea")
    c = simhash("quarterly revenue report for banks")
    print("similarity(different topics) ->", round(similarity(a, c), 4))

    two = compute_growth_acceleration(series([100, 200]), now=NOW)
    print("two points  -> growth", two.growth, "accel", two.acceleration, "has_accel", two.has_acceleration)

    three = compute_growth_acceleration(series([100, 200, 400]), now=NOW)
    print("three points-> growth", three.growth, "accel", three.acceleration, "has_accel", three.has_acceleration)


if __name__ == "__main__":
    main()