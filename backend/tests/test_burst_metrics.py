from app.pipeline.detection.metrics import poisson_cusum_burst_score


def test_poisson_cusum_ignores_a_single_isolated_item():
    assert poisson_cusum_burst_score([0] * 11 + [1]) == 0.0


def test_poisson_cusum_scores_sustained_arrival_rate_shift():
    assert poisson_cusum_burst_score([0] * 6 + [0, 0, 2, 2, 2, 2]) > 0.9


def test_poisson_cusum_does_not_call_a_flat_rate_a_burst():
    assert poisson_cusum_burst_score([1] * 12) == 0.0


def test_poisson_cusum_returns_zero_without_a_baseline_window():
    assert poisson_cusum_burst_score([0, 2, 3], baseline_bins=6) == 0.0
