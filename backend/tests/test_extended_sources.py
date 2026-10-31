from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.config import settings
from app.pipeline.collectors.adapters.bluesky_jetstream import _post_to_event, _websocket_url
from app.pipeline.collectors.custom_rss import configured_feed_urls
from app.pipeline.collectors.mastodon_trends import mastodon_instances
from app.pipeline.collectors.rss_utils import parse_feed


@pytest.mark.parametrize(
    ("xml", "expected_link", "expected_title"),
    [
        (
            '<rss><channel><item><title>Release &amp; update</title><link>https://example.test/a</link><pubDate>Tue, 28 Oct 2026 08:00:00 GMT</pubDate><description><![CDATA[<p>Useful story</p>]]></description></item></channel></rss>',
            "https://example.test/a",
            "Release & update",
        ),
        (
            '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Atom story</title><link rel="self" href="https://example.test/self"/><link href="https://example.test/story"/><updated>2026-10-28T08:00:00Z</updated><summary>Summary</summary></entry></feed>',
            "https://example.test/story",
            "Atom story",
        ),
        (
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/"><item><title>RDF story</title><link>https://example.test/rdf</link></item></rdf:RDF>',
            "https://example.test/rdf",
            "RDF story",
        ),
    ],
)
def test_parse_common_rss_atom_formats(xml, expected_link, expected_title):
    items = parse_feed(xml)
    assert items[0]["link"] == expected_link
    assert items[0]["title"] == expected_title


def test_extra_feed_list_is_bounded_and_rejects_credentials_and_non_http(monkeypatch):
    monkeypatch.setattr(
        settings,
        "extra_rss_feeds",
        "https://one.test/feed,ftp://bad.test/feed,https://user:pass@two.test/feed,https://three.test/rss",
    )
    monkeypatch.setattr(settings, "extra_rss_feed_limit", 10)
    assert configured_feed_urls() == [
        "https://one.test/feed",
        "https://three.test/rss",
    ]


def test_mastodon_instances_validate_hosts_and_cap_count(monkeypatch):
    monkeypatch.setattr(
        settings,
        "mastodon_instances",
        "mastodon.social,https://bad.test,foo..bar,one.test,two.test,three.test,four.test,five.test,six.test,ignored.test",
    )
    assert mastodon_instances() == [
        "mastodon.social",
        "one.test",
        "two.test",
        "three.test",
        "four.test",
        "five.test",
    ]


def test_mastodon_known_recurring_calendar_tags_are_filtered():
    from app.pipeline.collectors.mastodon_trends import LOW_SIGNAL_TAGS

    assert "tgif" in LOW_SIGNAL_TAGS
    assert "fursuitfriday" in LOW_SIGNAL_TAGS
    assert "security" not in LOW_SIGNAL_TAGS


def test_mastodon_only_keeps_tags_rising_today():
    from app.pipeline.collectors.mastodon_trends import _is_early_tag

    assert _is_early_tag(
        [{"uses": "68"}, {"uses": "19"}, {"uses": "26"}]
    )
    assert not _is_early_tag(
        [{"uses": "4"}, {"uses": "348"}, {"uses": "0"}]
    )
    assert not _is_early_tag(
        [{"uses": "150"}, {"uses": "59"}, {"uses": "166"}]
    )


def test_bluesky_jetstream_post_maps_to_signal_event():
    event = _post_to_event(
        {
            "did": "did:plc:creator",
            "time_us": 1_793_174_400_000_000,
            "commit": {
                "collection": "app.bsky.feed.post",
                "operation": "create",
                "rkey": "postkey",
                "record": {
                    "text": (
                        "A new open source AI research tool launched with a free "
                        "model and detailed documentation for developers today."
                    ),
                    "createdAt": "2026-10-28T08:00:00Z",
                },
            },
        }
    )
    assert event is not None
    assert event.external_id == "at://did:plc:creator/app.bsky.feed.post/postkey"
    assert event.hashtags == []
    assert "open source ai" in event.metadata["matched_topics"]
    assert "ai" in event.metadata["matched_topics"]
    assert event.published_at == datetime(2026, 10, 28, 8, tzinfo=UTC)
    assert "start=" in _websocket_url(
        "jetstream1.us-east.bsky.network",
        start=datetime(2026, 10, 28, tzinfo=UTC),
        end=datetime(2026, 10, 28, 0, 0, 5, tzinfo=UTC),
    )


def test_bluesky_sample_rejects_unrelated_chatter_and_crisis_content():
    def event(text: str):
        return _post_to_event(
            {
                "did": "did:plc:creator",
                "commit": {
                    "collection": "app.bsky.feed.post",
                    "operation": "create",
                    "rkey": "postkey",
                    "record": {"text": text},
                },
            }
        )

    assert event("A sufficiently long personal thought about my weekend and the weather outside today.") is None
    assert event("I want to die and end my life; no longer be alive is the only thing on my mind today. #AI") is None
