"""Read-only event-level backtest for mention-rate burst detection.

Run from the backend directory:
    .venv/Scripts/python.exe scripts/evaluate_burst_quality.py

The target is continuation: in the next horizon, a cluster gains at least one
more unique item than in the immediately preceding horizon, with two future
items minimum. This is a measurable event-volume proxy, not story importance.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline.detection.cross_velocity import get_collector_family
from app.pipeline.detection.metrics import poisson_cusum_burst_score


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=None)


def load_events(database: Path) -> dict[str, list[tuple[datetime, str]]]:
    connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            """
            SELECT cluster_id, source_id, external_id, canonical_url, text_hash,
                   id, observed_at
            FROM source_events
            WHERE cluster_id IS NOT NULL AND observed_at IS NOT NULL
            ORDER BY observed_at
            """
        ).fetchall()
    finally:
        connection.close()

    first_seen: dict[tuple[str, str, str], datetime] = {}
    for cluster, source, external, canonical, text_hash, event_id, observed in rows:
        when = parse_time(observed)
        family = get_collector_family(source or "")
        item = canonical or external or text_hash or event_id
        key = (cluster, family, item)
        previous = first_seen.get(key)
        if previous is None or when < previous:
            first_seen[key] = when

    events: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
    for (cluster, family, _item), when in first_seen.items():
        events[cluster].append((when, family))
    for history in events.values():
        history.sort()
    return events


def auc(pairs: list[tuple[float, bool]]) -> float | None:
    positives = sorted(score for score, label in pairs if label)
    negatives = sorted(score for score, label in pairs if not label)
    if not positives or not negatives:
        return None
    # Count wins/ties without a third-party dependency.
    import bisect

    wins = sum(
        bisect.bisect_left(negatives, score)
        + 0.5
        * (bisect.bisect_right(negatives, score) - bisect.bisect_left(negatives, score))
        for score in positives
    )
    return wins / (len(positives) * len(negatives))


def evaluate(events: dict[str, list[tuple[datetime, str]]], horizon: int) -> list[dict]:
    examples = []
    step = timedelta(minutes=5)
    lookback = timedelta(minutes=60)
    future = timedelta(minutes=horizon)
    for cluster, history in events.items():
        if len(history) < 4:
            continue
        start = history[0][0] + lookback
        end = history[-1][0] - future
        anchor = start.replace(second=0, microsecond=0)
        anchor += timedelta(minutes=(5 - anchor.minute % 5) % 5)
        while anchor <= end:
            prior_start = anchor - lookback
            recent_start = anchor - future
            recent = [when for when, _ in history if recent_start <= when < anchor]
            upcoming = [when for when, _ in history if anchor <= when < anchor + future]
            if len(recent) >= 2:
                buckets = [0] * 60
                for when, _ in history:
                    if prior_start <= when < anchor:
                        index = int((when - prior_start).total_seconds() // 60)
                        if 0 <= index < 60:
                            buckets[index] += 1
                score = poisson_cusum_burst_score(buckets, baseline_bins=30)
                examples.append(
                    {
                        "at": anchor,
                        "cusum": score,
                        "recent_rate": float(len(recent)),
                        "positive": len(upcoming) >= max(2, len(recent) + 1),
                    }
                )
            anchor += step
    return examples


def report(examples: list[dict], horizon: int) -> None:
    if not examples:
        print(f"{horizon}m: no eligible examples")
        return
    examples.sort(key=lambda item: item["at"])
    cutoff = examples[max(1, min(len(examples) - 1, int(len(examples) * 0.7)))] ["at"]
    train_cutoff = cutoff - timedelta(minutes=2 * horizon)
    train = [item for item in examples if item["at"] < train_cutoff]
    test = [item for item in examples if item["at"] >= cutoff]
    print(
        f"{horizon}m: n={len(examples)}, positive={sum(x['positive'] for x in examples)} "
        f"({sum(x['positive'] for x in examples) / len(examples):.1%}), "
        f"temporal train={len(train)}, holdout={len(test)}, embargo={len(examples)-len(train)-len(test)}"
    )
    for label, rows in (("all", examples), ("holdout", test)):
        for feature in ("cusum", "recent_rate"):
            result = auc([(item[feature], item["positive"]) for item in rows])
            print(f"  {label} AUC {feature}: {result if result is not None else 'n/a'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("signal_radar.db"))
    args = parser.parse_args()
    database = args.database.resolve()
    if not database.is_file():
        parser.error(f"SQLite database not found: {database}")
    events = load_events(database)
    total = sum(len(history) for history in events.values())
    print(f"Database: {database}")
    print(f"Clusters: {len(events):,}; unique cluster/family/items: {total:,}")
    if events:
        times = [history[0][0] for history in events.values()] + [history[-1][0] for history in events.values()]
        print(f"Coverage: {min(times).isoformat()} to {max(times).isoformat()}")
    print("Read-only; 5-minute anchors; 60-minute lookback; repeated polls deduplicated.")
    print("Outcome: future unique items >= max(2, recent-horizon items + 1).")
    for horizon in (15, 30):
        report(evaluate(events, horizon), horizon)


if __name__ == "__main__":
    main()
