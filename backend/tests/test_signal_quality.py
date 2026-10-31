from datetime import UTC, datetime, timedelta

from app.pipeline.signal_quality import (
    ForecastExample,
    Observation,
    calibration_report,
    collect_examples,
    rank_auc,
    precision_at_fraction,
    within_metric_auc,
)


def _point(signal_id: str, minutes: int, activity: float, strength: float, metric="views"):
    return Observation(
        signal_id=signal_id,
        observed_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=minutes),
        activity=activity,
        strength=strength,
        activity_metric=metric,
        source_id="test_source",
    )


def test_only_same_positive_metric_can_create_growth_outcome():
    rows = [
        _point("valid", 0, 100, 70),
        _point("valid", 15, 130, 20),
        _point("wrong-metric", 0, 100, 99),
        _point("wrong-metric", 15, 900, 1, metric="likes"),
        _point("zero", 0, 0, 80),
        _point("zero", 15, 100, 1),
        _point("unmeasured", 0, 100, 90, metric="news_mentions"),
        _point("unmeasured", 15, 500, 1, metric="news_mentions"),
    ]

    examples = collect_examples(rows, horizon_minutes=15)

    assert len(examples) == 1
    assert examples[0].signal_id == "valid"
    assert examples[0].grew is True


def test_strength_auc_and_temporal_holdout_calibration():
    examples = []
    for index in range(20):
        score = 80.0 if index % 2 == 0 else 10.0
        grew = index % 2 == 0
        examples.append(
            ForecastExample(
                signal_id=str(index),
                forecast_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index),
                strength=score,
                source_id="test",
                metric="views",
                start_activity=10.0,
                end_activity=13.0 if grew else 10.0,
                elapsed_minutes=30.0,
                grew=grew,
                features={"test_rank": score, "current_feed_order": score},
            )
        )

    assert rank_auc(examples) == 1.0
    assert rank_auc(examples, "test_rank") == 1.0
    assert within_metric_auc(examples, feature="test_rank")["auc"] == 1.0
    assert precision_at_fraction(examples, feature="strength")["precision"] == 1.0
    assert precision_at_fraction(examples, feature="current_feed_order")["precision"] == 1.0
    report = calibration_report(examples, min_bin_samples=2, embargo_minutes=0)
    assert report["samples"] == 20
    assert report["holdout"]["test_samples"] == 6
    assert report["holdout"]["train_end"] < report["holdout"]["test_start"]
    assert report["holdout"]["calibrated_brier"] < report["holdout"]["base_rate_brier"]


def test_top_slice_shares_partial_credit_across_ties():
    examples = [
        ForecastExample(
            signal_id=str(index),
            forecast_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index),
            strength=10.0,
            source_id="test",
            metric="views",
            start_activity=10.0,
            end_activity=13.0 if index % 2 == 0 else 10.0,
            elapsed_minutes=15.0,
            grew=index % 2 == 0,
            features={"rank": 1.0},
        )
        for index in range(20)
    ]

    assert precision_at_fraction(examples, feature="rank")["precision"] == 0.5
