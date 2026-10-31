"""Leakage-resistant evaluation of observed signal growth.

Signal strength is an activity ranking, not a probability. This module maps
historical strengths to a narrowly defined, measurable outcome without
silently treating the radar's own status label as ground truth.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import floor
from typing import Iterable


@dataclass(frozen=True)
class Observation:
    signal_id: str
    observed_at: datetime
    activity: float
    strength: float
    activity_metric: str | None
    source_id: str
    features: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ForecastExample:
    signal_id: str
    forecast_at: datetime
    strength: float
    source_id: str
    metric: str
    start_activity: float
    end_activity: float
    elapsed_minutes: float
    grew: bool
    features: dict[str, float] = field(default_factory=dict)


def collect_examples(
    observations: Iterable[Observation],
    *,
    horizon_minutes: int,
    growth_threshold: float = 0.20,
) -> list[ForecastExample]:
    """Take one earliest valid forecast per signal, with a 1x–2x horizon window.

    Only positive measurements in the exact same metric are comparable. An
    unmeasured news headline therefore cannot count as a failed forecast.
    """
    grouped: dict[str, list[Observation]] = defaultdict(list)
    for observation in observations:
        grouped[observation.signal_id].append(observation)

    examples: list[ForecastExample] = []
    for signal_id, history in grouped.items():
        history.sort(key=lambda item: item.observed_at)
        for index, current in enumerate(history[:-1]):
            if (
                not current.activity_metric
                or current.activity_metric in {"news_mentions", "unknown"}
                or current.activity <= 0
            ):
                continue

            target = None
            for future in history[index + 1 :]:
                elapsed = (future.observed_at - current.observed_at).total_seconds() / 60
                if elapsed > horizon_minutes * 2:
                    break
                if elapsed < horizon_minutes:
                    continue
                if (
                    future.activity_metric == current.activity_metric
                    and future.activity > 0
                ):
                    target = (future, elapsed)
                    break

            if target is None:
                continue
            future, elapsed = target
            examples.append(
                ForecastExample(
                    signal_id=signal_id,
                    forecast_at=current.observed_at,
                    strength=max(0.0, min(float(current.strength), 100.0)),
                    source_id=current.source_id,
                    metric=current.activity_metric,
                    start_activity=current.activity,
                    end_activity=future.activity,
                    elapsed_minutes=elapsed,
                    grew=future.activity >= current.activity * (1.0 + growth_threshold),
                    features=current.features,
                )
            )
            break  # one example per signal avoids overweighting frequent sources

    return sorted(examples, key=lambda item: item.forecast_at)


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial rate; zero-width samples stay unknown."""
    if total <= 0:
        return 0.0, 0.0
    rate = successes / total
    z2 = z * z
    denominator = 1.0 + z2 / total
    centre = (rate + z2 / (2.0 * total)) / denominator
    margin = z * ((rate * (1.0 - rate) / total + z2 / (4.0 * total**2)) ** 0.5) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def rank_auc(examples: list[ForecastExample], feature: str = "strength") -> float | None:
    """Pairwise ranking ability (Mann–Whitney AUC), with half credit for ties."""
    def value(item: ForecastExample) -> float | None:
        return item.strength if feature == "strength" else item.features.get(feature)

    positives = [score for item in examples if item.grew if (score := value(item)) is not None]
    negatives = [score for item in examples if not item.grew if (score := value(item)) is not None]
    if not positives or not negatives:
        return None
    negatives.sort()
    wins = sum(
        bisect_left(negatives, positive)
        + 0.5 * (bisect_right(negatives, positive) - bisect_left(negatives, positive))
        for positive in positives
    )
    return wins / (len(positives) * len(negatives))


def within_metric_auc(
    examples: list[ForecastExample], *, feature: str = "strength", min_group_samples: int = 20
) -> dict:
    """Weighted AUC within source+metric cohorts, reducing cross-source bias."""
    groups: dict[tuple[str, str], list[ForecastExample]] = defaultdict(list)
    for item in examples:
        groups[(item.source_id, item.metric)].append(item)
    eligible = []
    cohort_results = []
    for (source, metric), group in sorted(groups.items()):
        auc = rank_auc(group, feature)
        if len(group) >= min_group_samples and auc is not None:
            eligible.append((group, auc))
            cohort_results.append(
                {"source": source, "metric": metric, "samples": len(group), "auc": auc}
            )
    total = sum(len(group) for group, _ in eligible)
    if not total:
        return {"auc": None, "groups": 0, "samples": 0, "cohorts": []}
    weighted = sum(auc * len(group) for group, auc in eligible) / total
    return {
        "auc": weighted,
        "groups": len(eligible),
        "samples": total,
        "cohorts": cohort_results,
    }


def precision_at_fraction(
    examples: list[ForecastExample], *, feature: str, fraction: float = 0.10
) -> dict:
    """Expected hit rate in the top slice, sharing credit across tied scores."""
    ranked = []
    for item in examples:
        value = item.strength if feature == "strength" else item.features.get(feature)
        if value is not None:
            ranked.append((value, item.grew))
    if not ranked:
        return {"precision": None, "baseline": None, "lift": None, "top_n": 0}

    ranked.sort(key=lambda pair: pair[0], reverse=True)
    top_n = max(1, min(len(ranked), int(len(ranked) * fraction + 0.999999)))
    threshold = ranked[top_n - 1][0]
    above = [success for score, success in ranked if score > threshold]
    tied = [success for score, success in ranked if score == threshold]
    needed_from_tie = top_n - len(above)
    expected_hits = sum(above) + needed_from_tie * (sum(tied) / len(tied))
    precision = expected_hits / top_n
    baseline = sum(success for _, success in ranked) / len(ranked)
    return {
        "precision": precision,
        "baseline": baseline,
        "lift": precision / baseline if baseline else None,
        "top_n": top_n,
    }


def calibration_report(
    examples: list[ForecastExample],
    *,
    min_bin_samples: int = 25,
    embargo_minutes: int = 120,
) -> dict:
    """Describe score bands and evaluate a smoothed mapping on a time holdout.

    The first 70% of forecast time trains Beta(1, 1)-smoothed strength bands;
    the latest 30% are held out. A purge gap prevents overlapping outcome
    windows crossing the split. Sparse bands fall back to the training base rate.
    """
    examples = sorted(examples, key=lambda item: item.forecast_at)
    if not examples:
        return {"samples": 0, "bands": [], "auc": None, "holdout": None}

    base_rate = sum(item.grew for item in examples) / len(examples)
    buckets: dict[int, list[ForecastExample]] = defaultdict(list)
    for item in examples:
        buckets[min(floor(item.strength / 10.0) * 10, 90)].append(item)

    bands = []
    for lower, bucket in sorted(buckets.items()):
        successes = sum(item.grew for item in bucket)
        low, high = wilson_interval(successes, len(bucket))
        bands.append(
            {
                "range": f"{lower:02d}–{lower + 10:02d}",
                "samples": len(bucket),
                "growth_rate": successes / len(bucket),
                "wilson_95": (low, high),
            }
        )

    cut_index = max(1, min(len(examples) - 1, int(len(examples) * 0.70)))
    cutoff_time = examples[cut_index].forecast_at
    train_cutoff = cutoff_time - timedelta(minutes=max(embargo_minutes, 0))
    train = [item for item in examples if item.forecast_at < train_cutoff]
    test = [item for item in examples if item.forecast_at >= cutoff_time]
    gap_samples = len(examples) - len(train) - len(test)
    feature_names = sorted({name for item in examples for name in item.features})
    feature_auc = {
        name: {
            "all": rank_auc(examples, name),
            "holdout": rank_auc(test, name) if test else None,
            "within_metric": within_metric_auc(examples, feature=name),
            "within_metric_holdout": within_metric_auc(test, feature=name),
        }
        for name in feature_names
        if sum(name in item.features for item in examples) >= 20
    }
    top_slice = {
        feature: {
            "all": precision_at_fraction(examples, feature=feature),
            "holdout": precision_at_fraction(test, feature=feature),
        }
        for feature in (
            "strength",
            "current_feed_order",
            "status_evidence_order",
            "status_strength_order",
        )
    }
    if train and test:
        train_bins: dict[int, list[ForecastExample]] = defaultdict(list)
        for item in train:
            train_bins[min(floor(item.strength / 10.0) * 10, 90)].append(item)
        train_rate = sum(item.grew for item in train) / len(train)
        calibrated = {}
        for lower, bucket in train_bins.items():
            if len(bucket) >= min_bin_samples:
                # Uniform Beta(1,1) prior prevents 0%/100% claims from small bins.
                calibrated[lower] = (sum(item.grew for item in bucket) + 1) / (len(bucket) + 2)

        baseline_brier = sum((train_rate - float(item.grew)) ** 2 for item in test) / len(test)
        mapped_brier = sum(
            (calibrated.get(min(floor(item.strength / 10.0) * 10, 90), train_rate) - float(item.grew)) ** 2
            for item in test
        ) / len(test)
        holdout = {
            "train_samples": len(train),
            "test_samples": len(test),
            "embargoed_samples": gap_samples,
            "train_end": train[-1].forecast_at.isoformat(),
            "test_start": test[0].forecast_at.isoformat(),
            "base_rate_brier": baseline_brier,
            "calibrated_brier": mapped_brier,
            "calibrated_skill_vs_base": 1.0 - mapped_brier / baseline_brier if baseline_brier else None,
            "calibrated_bands": len(calibrated),
        }
    else:
        holdout = None

    return {
        "samples": len(examples),
        "successes": sum(item.grew for item in examples),
        "growth_rate": base_rate,
        "auc": rank_auc(examples),
        "auc_holdout": rank_auc(test),
        "within_metric_auc": within_metric_auc(examples),
        "within_metric_auc_holdout": within_metric_auc(test),
        "feature_auc": feature_auc,
        "top_slice": top_slice,
        "bands": bands,
        "holdout": holdout,
    }
