from app.pipeline.collectors.google_news_trends import _query_activity_metric


def test_google_news_metric_is_stable_for_the_same_query():
    assert _query_activity_metric("us", "when:1h", "AI agent") == (
        _query_activity_metric("US", "when:1h", " AI   AGENT ")
    )


def test_google_news_metric_separates_different_measurement_windows():
    assert _query_activity_metric("US", "when:1h", "AI agent") != (
        _query_activity_metric("US", "when:6h", "AI agent")
    )


def test_google_news_metric_separates_different_queries_and_countries():
    baseline = _query_activity_metric("US", "when:1h", "AI agent")
    assert baseline != _query_activity_metric("US", "when:1h", "viral trend")
    assert baseline != _query_activity_metric("GB", "when:1h", "AI agent")
