from app.pipeline.mentions import MentionObservation, summarize_cluster_mentions


def test_repeated_polls_of_the_same_item_count_once_at_first_seen_time():
    observations = [
        MentionObservation("story", "reddit", "post-1", 610),
        MentionObservation("story", "reddit", "post-1", 700),
        MentionObservation("story", "reddit", "post-1", 800),
    ]

    activity = summarize_cluster_mentions(observations, now=3_600)["story"]

    assert activity.density_count == 1
    assert sum(activity.interval_counts) == 1
    assert activity.interval_counts[10] == 1


def test_same_post_from_an_independent_family_is_a_second_observation():
    observations = [
        MentionObservation("story", "reddit", "same-url", 3_010),
        MentionObservation("story", "rss_news", "same-url", 3_020),
    ]

    activity = summarize_cluster_mentions(observations, now=3_600)["story"]

    assert activity.density_count == 2


def test_equal_minute_buckets_detect_sustained_new_arrivals():
    observations = [
        MentionObservation("story", "reddit", "post-a", 3_550),
        MentionObservation("story", "rss_news", "post-b", 3_551),
        MentionObservation("story", "github", "post-c", 3_552),
        MentionObservation("story", "mastodon", "post-d", 3_553),
    ]

    activity = summarize_cluster_mentions(observations, now=3_600)["story"]

    assert activity.interval_counts[-2:] == (0, 4)
    assert activity.burst_score > 0.5


def test_current_partial_minute_is_deferred_to_keep_equal_exposure():
    observations = [MentionObservation("story", "reddit", "new-post", 3_599)]

    activity = summarize_cluster_mentions(observations, now=3_599.5)

    assert activity == {}
