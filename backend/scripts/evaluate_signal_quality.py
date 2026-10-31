"""Read-only historical evaluation for Signal Radar's activity ranking.

Run from the backend directory:
    .venv/Scripts/python.exe scripts/evaluate_signal_quality.py
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline.signal_quality import (
    Observation,
    calibration_report,
    collect_examples,
)


def load_observations(database: Path) -> list[Observation]:
    connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            """
            SELECT snapshot.signal_id, snapshot.captured_at, snapshot.activity,
                   snapshot.previous_activity, snapshot.strength, snapshot.growth,
                   snapshot.acceleration, snapshot.status,
                   snapshot.extra, signal.source_id
            FROM signal_snapshots AS snapshot
            JOIN signals AS signal ON signal.id = snapshot.signal_id
            ORDER BY snapshot.signal_id, snapshot.captured_at
            """
        ).fetchall()
    finally:
        connection.close()

    observations = []
    for signal_id, captured_at, activity, previous_activity, strength, growth, acceleration, status, extra, source_id in rows:
        try:
            snapshot_extra = json.loads(extra or "{}")
            if not isinstance(snapshot_extra, dict):
                continue
            metric = snapshot_extra.get("activity_metric")
            observed_at = datetime.fromisoformat(captured_at)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        features = {
            "snapshot_growth": float(growth or 0.0),
            "snapshot_acceleration": float(acceleration or 0.0),
            "mention_burst_score": float(snapshot_extra.get("mention_burst_score") or 0.0),
            "density_count": float(snapshot_extra.get("density_count") or 0.0),
        }
        components = snapshot_extra.get("components") or {}
        for name, value in components.items():
            try:
                features[f"component_{name}"] = float(value)
            except (TypeError, ValueError):
                continue
        try:
            source_evidence = float(components.get("source_evidence_factor", 0.7))
        except (TypeError, ValueError):
            source_evidence = 0.7
        source_count_bucket = max(1, min(3, round((source_evidence - 0.7) / 0.1) + 1))
        status_rank = {"BREAKOUT": 0, "RISING": 1, "NEW": 2}.get(status, 3)
        if source_count_bucket > 1:
            evidence_tier = 0
        elif activity > 0 or previous_activity > 0 or growth > 0:
            evidence_tier = 1
        else:
            evidence_tier = 2
        # Mirrors the feed's evidence tier -> lifecycle -> strength SQL order.
        features["current_feed_order"] = (
            -evidence_tier * 10_000 - status_rank * 100 + float(strength or 0.0)
        )
        features["status_evidence_order"] = (
            -status_rank * 10_000 - evidence_tier * 100 + float(strength or 0.0)
        )
        features["status_strength_order"] = (
            -status_rank * 1_000_000
            + float(strength or 0.0) * 100
            - evidence_tier * 10
            + source_count_bucket
        )
        observations.append(
            Observation(
                signal_id=signal_id,
                observed_at=observed_at,
                activity=float(activity or 0.0),
                strength=float(strength or 0.0),
                activity_metric=metric,
                source_id=source_id,
                features=features,
            )
        )
    return observations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("signal_radar.db"),
        help="SQLite database path (read-only; defaults to backend/signal_radar.db)",
    )
    parser.add_argument(
        "--growth-threshold",
        type=float,
        default=0.20,
        help="Minimum relative activity increase for a positive outcome (default: 0.20)",
    )
    args = parser.parse_args()
    database = args.database.resolve()
    if not database.is_file():
        parser.error(f"SQLite database not found: {database}")

    observations = load_observations(database)
    timestamps = [item.observed_at for item in observations]
    print(f"Database: {database}")
    print(f"Snapshots: {len(observations):,}")
    if timestamps:
        print(f"Coverage: {min(timestamps).isoformat()} to {max(timestamps).isoformat()}")
    print(f"Outcome: same positive activity metric grows by >= {args.growth_threshold:.0%}")
    print("One earliest eligible sample per signal; future window is horizon to 2x horizon.")
    print("Strength remains a ranking; empirical mapping is evaluated on a later time holdout.")

    for horizon in (15, 30, 60):
        examples = collect_examples(
            observations,
            horizon_minutes=horizon,
            growth_threshold=args.growth_threshold,
        )
        report = calibration_report(examples, embargo_minutes=horizon * 2)
        print(f"\n{horizon}-minute outcome: {report['successes']}/{report['samples']} grew")
        if report["samples"]:
            within = report["within_metric_auc"]
            within_auc = "n/a" if within["auc"] is None else f"{within['auc']:.3f}"
            holdout_auc = "n/a" if report["auc_holdout"] is None else f"{report['auc_holdout']:.3f}"
            within_holdout = report["within_metric_auc_holdout"]
            within_holdout_auc = "n/a" if within_holdout["auc"] is None else f"{within_holdout['auc']:.3f}"
            print(
                f"  observed rate: {report['growth_rate']:.1%}; "
                f"strength AUC pooled={report['auc']:.3f}, holdout={holdout_auc}, "
                f"within-source/metric={within_auc} "
                f"({within['groups']} cohorts, {within['samples']} signals), "
                f"holdout within-cohort={within_holdout_auc} "
                f"({within_holdout['groups']} cohorts)"
            )
            for cohort in within["cohorts"]:
                print(
                    f"    {cohort['source']}/{cohort['metric']}: "
                    f"n={cohort['samples']}, AUC={cohort['auc']:.3f}"
                )
            candidate_features = {
                "component_recency",
                "component_staleness_factor",
                "snapshot_growth",
                "snapshot_acceleration",
                "component_velocity",
                "component_persistence",
                "component_cross_source",
                "current_feed_order",
                "status_evidence_order",
                "status_strength_order",
                "mention_burst_score",
                "density_count",
            }
            feature_aucs = [
                (name, aucs)
                for name, aucs in report["feature_auc"].items()
                if name in candidate_features
            ]
            feature_aucs.sort(
                key=lambda item: item[1]["holdout"] if item[1]["holdout"] is not None else -1,
                reverse=True,
            )
            if feature_aucs:
                print("  feature AUC (pooled / later holdout / within-cohort / holdout within-cohort):")
                for name, aucs in feature_aucs:
                    holdout_auc = "n/a" if aucs["holdout"] is None else f"{aucs['holdout']:.3f}"
                    within_feature_auc = aucs["within_metric"]["auc"]
                    within_text = "n/a" if within_feature_auc is None else f"{within_feature_auc:.3f}"
                    within_holdout_auc = aucs["within_metric_holdout"]["auc"]
                    within_holdout_text = "n/a" if within_holdout_auc is None else f"{within_holdout_auc:.3f}"
                    print(
                        f"    {name}: {aucs['all']:.3f} / {holdout_auc} / "
                        f"{within_text} / {within_holdout_text}"
                    )
            print("  top-10% growth precision (all / later holdout; lift over base):")
            for name, results in report["top_slice"].items():
                all_result = results["all"]
                holdout_result = results["holdout"]
                all_precision = "n/a" if all_result["precision"] is None else f"{all_result['precision']:.1%}"
                test_precision = "n/a" if holdout_result["precision"] is None else f"{holdout_result['precision']:.1%}"
                lift = "n/a" if holdout_result["lift"] is None else f"{holdout_result['lift']:.2f}x"
                print(f"    {name}: {all_precision} / {test_precision}; holdout lift={lift}")
        print("  strength band | n | observed growth | Wilson 95% interval")
        for band in report["bands"]:
            low, high = band["wilson_95"]
            print(
                f"  {band['range']:>11} | {band['samples']:>3} | "
                f"{band['growth_rate']:>15.1%} | {low:.1%}–{high:.1%}"
            )
        holdout = report["holdout"]
        if holdout:
            print(
                "  later-time holdout: "
                f"train={holdout['train_samples']}, test={holdout['test_samples']}, "
                f"purged gap={holdout['embargoed_samples']}, "
                f"calibrated bins={holdout['calibrated_bands']}"
            )
            print(
                f"  Brier: calibrated={holdout['calibrated_brier']:.4f}, "
                f"training base rate={holdout['base_rate_brier']:.4f}, "
                f"skill={holdout['calibrated_skill_vs_base']}"
            )
            print(f"  split: {holdout['train_end']} / {holdout['test_start']}")


if __name__ == "__main__":
    main()
