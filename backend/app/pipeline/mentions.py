"""Fixed-time mention buckets and unique-item density for signal clusters."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from app.pipeline.detection.cross_velocity import get_collector_family
from app.pipeline.detection.metrics import poisson_cusum_burst_score


@dataclass(frozen=True)
class MentionObservation:
    cluster_id: str
    source_id: str
    item_id: str
    observed_at: float


@dataclass(frozen=True)
class ClusterActivity:
    density_count: int
    interval_counts: tuple[int, ...]
    burst_score: float


def summarize_cluster_mentions(
    observations: list[MentionObservation],
    *,
    now: float,
    interval_seconds: int = 60,
    interval_count: int = 60,
    baseline_bins: int = 30,
) -> dict[str, ClusterActivity]:
    """Count distinct source-family items in equal one-minute intervals.

    Repeated polls of the same post/article count once, at its first observation
    in the window. This prevents collection cadence from masquerading as a burst.
    """
    interval_seconds = max(int(interval_seconds), 1)
    interval_count = max(int(interval_count), 2)
    # Stable time boundaries keep every sample the same duration. The current
    # incomplete minute is intentionally excluded; delay is at most one minute.
    window_end = (int(now) // interval_seconds) * interval_seconds
    window_start = window_end - interval_seconds * interval_count

    first_observation: dict[tuple[str, str, str], float] = {}
    for observation in observations:
        observed_at = float(observation.observed_at)
        if observed_at < window_start or observed_at >= window_end:
            continue
        family = get_collector_family(observation.source_id)
        key = (observation.cluster_id, family, observation.item_id)
        previous = first_observation.get(key)
        if previous is None or observed_at < previous:
            first_observation[key] = observed_at

    counts_by_cluster: dict[str, list[int]] = defaultdict(lambda: [0] * interval_count)
    for (cluster_id, _family, _item_id), observed_at in first_observation.items():
        index = min(
            int((observed_at - window_start) // interval_seconds), interval_count - 1
        )
        counts_by_cluster[cluster_id][index] += 1

    result = {}
    for cluster_id, counts in counts_by_cluster.items():
        result[cluster_id] = ClusterActivity(
            density_count=sum(counts),
            interval_counts=tuple(counts),
            burst_score=poisson_cusum_burst_score(
                counts,
                baseline_bins=min(max(baseline_bins, 1), interval_count - 1),
            ),
        )
    return result
