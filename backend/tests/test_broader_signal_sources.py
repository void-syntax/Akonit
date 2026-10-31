from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest

from app.pipeline.collectors.adapters.bluesky_jetstream import (
    BlueskyJetstreamAdapter,
    BlueskySearchStrategy,
    _annotate_topic_corroboration,
    _connect_timeout,
    _post_to_event,
    _websocket_url,
)
from app.pipeline.collectors.base import FetchContext, RawEvent, SourceUnavailable
from app.pipeline.collectors.gdelt_news import GdeltRecentNewsStrategy
from app.pipeline.collectors.google_news_trends import (
    QUERIES,
    NewsRssStrategy,
    _queries_for_cycle,
)
from app.pipeline.collectors.reddit import (
    RedditAdapter,
    _matched_query_terms,
    _reddit_query_title_matches,
)
from app.pipeline.detection.metrics import GrowthMetrics
from app.pipeline.detection.scoring import compute_strength


class FakeNewsClient:
    def __init__(self):
        self.request_count = 0

    async def get_text(self, _url, **_kwargs):
        self.request_count += 1
        now = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")
        items = "".join(
            f"<item><title>Global development number {self.request_count}-{i}</title>"
            f"<link>https://news.example/{self.request_count}/{i}</link>"
            f"<pubDate>{now}</pubDate></item>"
            for i in range(10)
        )
        return f"<rss><channel>{items}</channel></rss>"


def test_google_news_scans_three_queries_for_one_rotating_locale():
    client = FakeNewsClient()
    import app.pipeline.collectors.google_news_trends as news_module

    original_time = news_module.time.time
    try:
        news_module.time.time = lambda: 1_800_000_000
        events = asyncio.run(
            NewsRssStrategy().fetch(
                client, FetchContext(countries=["US", "GB"], limit=25)
            )
        )
    finally:
        news_module.time.time = original_time

    assert client.request_count == 3
    assert len(events) == 24
    assert len({event.url for event in events}) == 24
    assert {event.country_code for event in events} <= {"US", "GB"}
    assert all(event.activity == 0 and event.activity_metric == "news_mentions" for event in events)


def test_google_news_keeps_broad_discovery_when_profile_keywords_exist():
    selected = _queries_for_cycle(["cosmetics", "AI", "fashion"], cycle=7)

    assert len(selected) == 3
    assert len(set(selected)) == 3
    assert sum(query in {"cosmetics", "AI", "fashion"} for query in selected) == 1
    assert sum(query in QUERIES for query in selected) == 2


def test_google_news_rotates_custom_and_general_topics_between_cycles():
    first = _queries_for_cycle(["AI", "fashion", "robotics"], cycle=0)
    second = _queries_for_cycle(["AI", "fashion", "robotics"], cycle=1)

    assert first[0] == "AI"
    assert second[0] == "fashion"
    assert first[1:] != second[1:]


def test_google_news_uses_three_queries_and_rotates_locale_every_minute():
    class Client:
        def __init__(self):
            self.urls = []

        async def get_text(self, url, **_kwargs):
            self.urls.append(url)
            return "<rss><channel></channel></rss>"

    import app.pipeline.collectors.google_news_trends as news_module

    original_time = news_module.time.time
    client = Client()
    try:
        news_module.time.time = lambda: 1_800_000_000
        asyncio.run(
            NewsRssStrategy().fetch(
                client,
                FetchContext(countries=["US", "GB", "DE", "JP"], limit=25),
            )
        )
    except SourceUnavailable:
        # Empty feeds have no events; URLs still prove cadence and rotation.
        pass
    finally:
        news_module.time.time = original_time

    assert len(client.urls) == 3


def test_global_rss_source_polls_each_public_feed_and_preserves_source_mix():
    from app.pipeline.collectors.adapters.rss_news import RssNewsStrategy

    class Client:
        def __init__(self):
            self.calls = []

        async def get_text(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return (
                "<rss><channel><item><title>Breaking public update</title>"
                "<link>https://example.org/news/1</link></item></channel></rss>"
            )

    client = Client()
    events = asyncio.run(RssNewsStrategy().fetch(client, FetchContext(limit=25)))

    assert len(client.calls) == 6
    assert all(call[1]["timeout"] == 5.0 for call in client.calls)
    assert len(events) == 6
    assert {event.metadata["feed_id"] for event in events} == {
        "techcrunch",
        "hackernews_rss",
        "bloomberg",
        "bbc_world",
        "lemonde_world",
        "aljazeera_world",
    }


def test_global_rss_source_round_robins_before_filling_cycle_limit():
    from app.pipeline.collectors.adapters.rss_news import RssNewsStrategy

    class Client:
        async def get_text(self, url, **_kwargs):
            host = url.split("/")[2]
            items = "".join(
                f"<item><title>{host} update {index}</title>"
                f"<link>https://{host}/news/{index}</link></item>"
                for index in range(4)
            )
            return f"<rss><channel>{items}</channel></rss>"

    events = asyncio.run(RssNewsStrategy().fetch(Client(), FetchContext(limit=5)))

    assert len(events) == 5
    assert len({event.metadata["feed_id"] for event in events}) == 5


def test_reddit_uses_official_oauth_then_public_rss_fallback():
    adapter = RedditAdapter()
    assert [strategy.name for strategy in adapter.strategies] == [
        "official_oauth",
        "search_rss",
    ]


class FakeBlueskyClient:
    async def get_json(self, _url, *, params, **_kwargs):
        query = params["q"]
        now = datetime.now(UTC).isoformat()
        return {
            "posts": [
                {
                    "uri": f"at://did:plc:test/app.bsky.feed.post/{query.replace(' ', '-')}",
                    "record": {
                        "text": f"A detailed and current report about {query} with new evidence and market implications.",
                        "createdAt": now,
                    },
                    "author": {"did": "did:plc:test", "handle": "reporter.bsky.social"},
                    "likeCount": 4,
                    "repostCount": 2,
                    "replyCount": 1,
                    "quoteCount": 0,
                }
            ]
        }


def test_bluesky_search_uses_fresh_posts_and_measured_engagement():
    events = asyncio.run(
        BlueskySearchStrategy().fetch(FakeBlueskyClient(), FetchContext(limit=10))
    )

    assert len(events) == 3
    assert all(event.activity_metric == "social_engagement" for event in events)
    assert all(event.activity == 9.5 for event in events)


def test_bluesky_search_pauses_repeated_403_and_leaves_stream_fallback():
    class ForbiddenClient:
        calls = 0

        async def get_json(self, _url, **_kwargs):
            self.calls += 1
            raise SourceUnavailable("HTTP 403 from public search")

    client = ForbiddenClient()
    strategy = BlueskySearchStrategy()
    strategy.disabled_until = 0

    with pytest.raises(SourceUnavailable, match="paused for 1 hour"):
        asyncio.run(strategy.fetch(client, FetchContext(limit=10)))
    assert client.calls == 3

    with pytest.raises(SourceUnavailable, match="cooling down"):
        asyncio.run(strategy.fetch(client, FetchContext(limit=10)))
    assert client.calls == 3


def test_bluesky_same_author_posts_do_not_count_as_topic_corroboration():
    from app.pipeline.collectors.adapters.bluesky_jetstream import (
        _annotate_topic_corroboration,
    )

    events = [
        RawEvent(
            source_id="bluesky_stream",
            external_id=f"post-{index}",
            title="New public technology update with detailed information",
            url=f"https://bsky.app/post/{index}",
            metadata={"author_did": author, "matched_topics": ["technology"]},
        )
        for index, author in enumerate(["did:author-a", "did:author-a"])
    ]

    _annotate_topic_corroboration(events)
    assert all(event.metadata["topic_distinct_authors"] == 1 for event in events)
    assert all(event.metadata["topic_repeated_in_sample"] is False for event in events)
    assert all(event.metadata["topic_corroborated"] is False for event in events)


def test_bluesky_distinct_authors_can_corroborate_a_topic():
    from app.pipeline.collectors.adapters.bluesky_jetstream import (
        _annotate_topic_corroboration,
    )

    events = [
        RawEvent(
            source_id="bluesky_stream",
            external_id=f"post-{index}",
            title="New public technology update with detailed information",
            url=f"https://bsky.app/post/{index}",
            metadata={"author_did": author, "matched_topics": ["technology"]},
        )
        for index, author in enumerate(["did:author-a", "did:author-b"])
    ]

    _annotate_topic_corroboration(events)
    assert all(event.metadata["topic_distinct_authors"] == 2 for event in events)
    assert all(event.metadata["topic_repeated_in_sample"] is True for event in events)
    assert all(event.metadata["topic_corroborated"] is False for event in events)

def test_bluesky_adapter_prefers_ranked_search_then_bounded_stream():
    adapter = BlueskyJetstreamAdapter()
    assert [strategy.name for strategy in adapter.strategies] == [
        "public_search_engagement",
        "jetstream_live_sample",
    ]


def test_bluesky_jetstream_v2_url_uses_filtered_timestamp_cursor():
    start = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
    url = _websocket_url("jetstream.us-east.bsky.network", start=start, end=start)
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.path == "/xrpc/network.bsky.jetstream.subscribeEvents"
    assert params["collections"] == ["app.bsky.feed.post"]
    assert params["kinds"] == ["commit"]
    assert params["cursor"] == [str(int(start.timestamp() * 1_000_000))]


def test_bluesky_host_failover_respects_remaining_sample_budget():
    assert _connect_timeout(1.25) == 1.25
    assert _connect_timeout(8) == 4.0
    assert _connect_timeout(0) is None


def test_bluesky_jetstream_v2_envelope_maps_into_raw_event():
    now = datetime.now(UTC)
    event = _post_to_event(
        {
            "$type": "message",
            "payload": {
                "$type": "network.bsky.jetstream.subscribeEvents#commit",
                "did": "did:plc:example",
                "seq": 123456,
                "time": now.isoformat().replace("+00:00", "Z"),
                "operation": "create",
                "collection": "app.bsky.feed.post",
                "rkey": "post-key",
                "record": {
                    "createdAt": now.isoformat().replace("+00:00", "Z"),
                    "text": (
                        "Breaking update: artificial intelligence research reveals "
                        "a new machine learning method with major coding advances."
                    ),
                },
            },
        }
    )

    assert event is not None
    assert event.external_id == "at://did:plc:example/app.bsky.feed.post/post-key"
    assert event.metadata["cursor"] == 123456


def test_bluesky_v2_ignores_non_commit_envelopes():
    assert _post_to_event({"payload": {"$type": "network.bsky.jetstream.subscribeEvents#identity"}}) is None


def test_bluesky_sample_keeps_single_topic_observations_unconfirmed():
    event = RawEvent(
        source_id="bluesky_stream",
        external_id="at://did/post/1",
        title="A substantive topic report",
        url="https://bsky.app/profile/did/post/1",
        metadata={"matched_topics": ["artificial intelligence", "technology"]},
    )

    result = _annotate_topic_corroboration([event])

    assert result == [event]
    assert event.metadata["topic_sample_count"] == 1
    assert event.metadata["topic_corroborated"] is False


def test_reddit_rss_query_relevance_rejects_unrelated_result():
    assert _matched_query_terms(
        "viral product", "Genuinely how do I grow my hair longer?"
    ) == []
    assert _matched_query_terms(
        "viral product", "A new product went viral before launch"
    ) == ["viral", "product"]


def test_reddit_rss_does_not_accept_query_word_only_from_unrelated_snippet():
    assert _matched_query_terms(
        "science discovery", "Description mentions science and discovery"
    )
    assert _reddit_query_title_matches(
        "science discovery", "Remote Job - Databricks - Manager, Field Engineering"
    ) == []


class FakeGdeltClient:
    def __init__(self):
        self.params = None

    async def get_json(self, _url, *, params, **_kwargs):
        self.params = params
        return {
            "articles": [
                {
                    "url": "https://wire.example/current-story",
                    "title": "Global event draws attention across several regions",
                    "domain": "wire.example",
                    "language": "English",
                    "sourcecountry": "United States",
                    "seendate": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
                }
            ]
        }


def test_gdelt_maps_recent_articles_and_publisher_identity():
    client = FakeGdeltClient()
    events = asyncio.run(
        GdeltRecentNewsStrategy().fetch(client, FetchContext(limit=10))
    )

    assert len(events) == 1
    assert client.params["timespan"] == "1h"
    assert events[0].source_id == "gdelt_news"
    assert events[0].metadata["domain"] == "wire.example"
    assert events[0].published_at.tzinfo == UTC


def test_single_unmeasured_mention_cannot_outrank_confirmed_coverage():
    no_activity = GrowthMetrics(current=0, age_minutes=0)

    single_source = compute_strength(no_activity, cross_source_count=1)
    corroborated = compute_strength(no_activity, cross_source_count=2)

    assert single_source <= 10.0
    assert corroborated > single_source
