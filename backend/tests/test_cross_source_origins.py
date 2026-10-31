from app.services.pipeline_service import (
    _cross_source_family_count,
    _cross_source_origin,
)


def test_hacker_news_rss_mirror_is_not_an_independent_source():
    assert _cross_source_origin("hackernews") == _cross_source_origin(
        "rss_news", {"feed_id": "hackernews_rss"}
    )


def test_distinct_rss_publication_remains_a_distinct_origin():
    assert _cross_source_origin("rss_news", {"feed_id": "bbc_world"}) == (
        "rss:bbc_world"
    )


def test_social_reposts_do_not_count_as_independent_corroboration():
    assert _cross_source_family_count({"bluesky_stream", "mastodon"}) == 1


def test_independent_news_and_social_origins_count_separately():
    assert _cross_source_family_count({"google_news_trends", "bluesky_stream"}) == 2


def test_hacker_news_and_its_rss_mirror_count_once():
    origins = {
        _cross_source_origin("hackernews"),
        _cross_source_origin("rss_news", {"feed_id": "hackernews_rss"}),
    }
    assert _cross_source_family_count(origins) == 1
