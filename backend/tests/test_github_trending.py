from app.pipeline.collectors.github_trending import _activity_for_repo


def test_github_trending_keeps_lifetime_stars_out_of_daily_metric():
    assert _activity_for_repo({"stars_today": 0, "total_stars": 104281}) == (
        104281.0,
        "total_stars",
    )


def test_github_trending_marks_missing_counts_unmeasured():
    assert _activity_for_repo({"stars_today": 0, "total_stars": 0}) == (
        0.0,
        "unmeasured",
    )


def test_github_trending_prefers_daily_gain_when_available():
    assert _activity_for_repo({"stars_today": 37, "total_stars": 104281}) == (
        37.0,
        "stars_today",
    )
