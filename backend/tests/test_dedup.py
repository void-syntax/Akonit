from datetime import UTC, datetime, timedelta

from app.pipeline.dedup.dedup import ClusterCandidate, find_cluster, should_merge_cross_source
from app.pipeline.normalization.normalizer import simhash
from app.pipeline.collectors.base import RawEvent


def candidate(*, cluster="existing", source="reddit", text="New battery breakthrough raises energy density", url="https://example.com/story", age_minutes=1):
    observed = datetime.now(UTC) - timedelta(minutes=age_minutes)
    return ClusterCandidate(cluster, source, url, simhash(text), observed.timestamp())


def test_recent_cross_source_similar_text_merges():
    result = find_cluster(
        "New battery breakthrough raises energy density",
        "New battery breakthrough raises energy density",
        "https://other.example/story", "news", "item-2", [candidate()],
    )
    assert result.cluster_id == "existing"


def test_stale_candidate_does_not_merge():
    result = find_cluster(
        "New battery breakthrough raises energy density", "Researchers report results",
        "https://other.example/story", "news", "item-2",
        [candidate(age_minutes=60 * 24)], window_minutes=60,
    )
    assert result.is_new_cluster


def test_cross_source_threshold_is_stricter():
    assert should_merge_cross_source("reddit", "reddit", 0.8, min_score=0.8)
    assert not should_merge_cross_source("reddit", "news", 0.8, min_score=0.8)


def test_same_canonical_url_merges_across_sources():
    result = find_cluster(
        "Different title", "", "https://example.com/story?utm_source=x",
        "news", "item-2", [candidate(text="Unrelated text")],
    )
    assert result.cluster_id == "existing"


def test_relative_url_does_not_merge_across_sources():
    result = find_cluster(
        "Different title",
        "",
        "/status",
        "news",
        "item-2",
        [candidate(url="/status", text="Unrelated text")],
    )

    assert result.is_new_cluster


def test_observation_time_is_not_publication_time():
    published = datetime.now(UTC) - timedelta(days=3)
    event = RawEvent(
        source_id="news", external_id="item", title="A fresh title", url="https://example.com",
        published_at=published,
    )
    assert event.observed_at > published
