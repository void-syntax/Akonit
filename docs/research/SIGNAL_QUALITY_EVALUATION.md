# Signal quality measurement

## What is measured

`backend/scripts/evaluate_signal_quality.py` evaluates the existing activity score without changing it. For each signal, it takes the earliest eligible snapshot and compares it with the first later snapshot between one and two horizons away. A positive outcome means the same, positive, measured activity metric increased by at least 20%. Unmeasured news mentions and mismatched metric units are excluded. Each signal contributes at most one example per horizon.

The horizons are 15, 30, and 60 minutes. The outcome measures short term growth in the provider's reported metric. It does **not** mean that the story was true, important, viral, commercially successful, or useful to a person.

## How the evaluation avoids easy traps

- AUC checks whether stronger scores rank future growth above non-growth. It is reported pooled and within source-plus-metric cohorts, so source mix does not masquerade as ranking skill.
- Descriptive score bands use ten-point ranges and Wilson intervals. The training-only strength-to-rate mapping uses a Beta(1,1) prior and a minimum of 25 examples per band; sparse bands fall back to the training base rate.
- The forecast time at the 70%-of-samples mark starts the holdout. A purge gap of twice the horizon prevents training outcomes that overlap the test period.
- The calibrated map is scored with Brier score against the training base-rate forecast. Negative skill means the mapping was worse than that simple baseline.
- Wilson intervals show how uncertain observed rates are, especially for thin high-score bands.

The Brier score is a proper scoring rule for probability forecasts; the project first maps scores to empirical rates and tests that mapping on later data rather than treating the raw 0–100 strength as a probability ([Gneiting & Raftery, 2007](https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf)). The Brier decomposition separates reliability from resolution and base uncertainty ([Murphy, 1973](https://doi.org/10.1175/1520-0450(1973)012%3C0595:ANVPOT%3E2.0.CO;2)). Wilson intervals were selected for small binomial samples instead of the unstable normal approximation ([Wilson, 1927](https://doi.org/10.1080/01621459.1927.10502953)).

## First read of the local database

Read-only run on 2026-10-30 UTC:

| Horizon | Eligible signals | Grew by 20% | Pooled strength AUC | Within-source/metric AUC | Calibration skill vs base rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| 15 min | 323 | 67 (20.7%) | 0.518 | 0.768 across 4 cohorts / 158 signals | -0.243 |
| 30 min | 343 | 80 (23.3%) | 0.452 | 0.632 across 4 cohorts / 157 signals | -0.100 |
| 60 min | 272 | 83 (30.5%) | 0.437 | 0.657 across 4 cohorts / 144 signals | -0.073 |

I also backtested feed-order variants. The current evidence-tier → lifecycle-status → strength order reached within-source/metric AUC 0.782 / 0.702 / 0.707 for 15 / 30 / 60 minutes. Its later-time pooled AUC was 0.829 / 0.613 / 0.721, but no source-plus-metric holdout cohort had 20 examples. Tie-adjusted top-10% precision was weak and inconsistent: 0% / 0% / 22.2% in the later-time holdout, versus 27.3% / 9.1% / 22.2% for strength-only. That conflict says this outcome is not enough to select a universal feed order. Cross-source corroboration may carry value this outcome does not measure.

These results do not justify changing production score weights yet. Pooled strength AUC is near random at 15 minutes and below random at 30 and 60 minutes. Cohort-level results vary widely, and no source-plus-metric group had enough examples in the time holdout for a stable within-cohort AUC. The calibrated map loses to the base rate at every horizon. A few apparently strong score bands have very wide Wilson intervals because they contain only 1–11 examples.

Recency was a promising candidate in the current sample (within-cohort AUC about 0.79–0.81 across horizons), but its later-time within-cohort test did not have enough samples. It is an experiment to keep measuring, not a validated new weight. The history spans only about 33 hours, which is too short and too narrow to call the score calibrated.

## Run it again

From the `backend` directory:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_signal_quality.py
```

The script opens the SQLite database read-only. It accepts `--database` and `--growth-threshold` overrides. Keep collecting; rerun after multiple weeks and compare the same targets. Only consider a production scoring change when the candidate beats the base rate on a later-time holdout and the result repeats across multiple source-plus-metric cohorts.

For new event discovery, a separate follow-up is to compare burst detectors against these same time-held-out outcomes. Kleinberg's stream model treats topic bursts as state transitions and is a relevant candidate for event-level volume ([Cornell technical report](https://ecommons.cornell.edu/entities/publication/04b75865-7103-4954-a660-ee6c38e5e9a5)). It should be evaluated against the current robust median/MAD burst score before replacement.

## Low-cost mention-rate detector (experimental)

The ingestion path now computes mention density from unique `(cluster, collector family, item)` observations, placing each item's first observation in a fixed one-minute bucket. Repeated polling of the same post/article no longer looks like new activity. The current partial minute is omitted, which bounds the added detection delay to one minute. The last half of the configured window is compared with the first half using a one-sided Poisson likelihood-ratio CUSUM with a small Gamma prior; the result is a bounded activity-surprise score, not a probability or calibrated confidence. It remains in the mention-only absolute-activity component and does not change the ranking weights.

This design follows the use of exposure-aware likelihood-ratio CUSUMs for Poisson counts ([Ryan & Woodall, 2010](https://doi.org/10.1080/00224065.2010.11917823)). Real social streams can be autocorrelated or seasonal, so Poisson independence is an approximation; methods that account for serial correlation/seasonality are a relevant next comparison ([Pignatiello et al., 2018](https://doi.org/10.1080/08982112.2018.1508696)). The current measured-activity evaluator is not a validation of this mention detector. Collect clean event-level history and compare false-alert rate and lead time before tuning its threshold or treating it as predictive.

`backend/scripts/evaluate_burst_quality.py` now performs a read-only event-level check. It deduplicates to the first observation of each cluster/family/item, scores on 5-minute anchors from a 60-minute lookback, and measures whether unique items continue in the next 15 or 30 minutes. On the local database (2026-10-31), there were only 34 eligible 15-minute examples and 52 30-minute examples. Temporal holdouts had 12 and 16 examples respectively. Holdout AUC was 0.864 for CUSUM at 15 minutes and 0.491 at 30 minutes; a raw recent-count comparator scored 0.182 and 0.718. These tiny, sparse holdouts are unstable and the outcome is only event-volume continuation. The CUSUM is therefore logged as an experimental diagnostic and is not used in the production strength ranking. Unique-item density correction is retained because it fixes repeated polling being counted as new mentions.

## Collection latency work

The collector previously awaited every due source with `gather()` before it stored any result. It now processes and commits each source as its fetch completes, while the other sources continue in the background; the UI's 15-second polling can therefore see early results before the slowest provider finishes. A compact timing log records time to first result, slowest fetch, persistence time, and total cycle time. The scheduling cadence and request concurrency remain bounded for a low-powered computer.

The candidate-loader query was measured against the local SQLite history. With 35,860 clustered event rows and 1,916 within the active lookback window, the query took about 0.40 seconds using the old cluster-only plan. Adding `(observed_at, cluster_id)` let SQLite seek to the recent range; the same query took 0.009–0.020 seconds across five runs, with `EXPLAIN QUERY PLAN` confirming use of the new index. This is a local measurement, not a guaranteed speedup for every database size. SQLite's query planner documentation describes using multicolumn indexes to narrow `WHERE` ranges ([SQLite Query Planning](https://www.sqlite.org/queryplanner.html)). Completion-order processing uses Python's standard `asyncio.as_completed`, which yields results as each task finishes ([Python asyncio documentation](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.as_completed)).
