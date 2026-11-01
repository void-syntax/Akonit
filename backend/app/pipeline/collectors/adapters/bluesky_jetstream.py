"""Bounded live Bluesky post sampling from its public Jetstream WebSocket."""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlunparse

from app.core.logging import get_logger
from app.models.enums import SourceType
from app.pipeline.collectors.base import (
    FetchContext,
    FetchResult,
    RawEvent,
    SourceAdapter,
    SourceUnavailable,
    Strategy,
)
from app.pipeline.collectors.registry import register_source, run_strategy_cascade

logger = get_logger(__name__)

JETSTREAM_HOSTS = (
    "jetstream.us-east.bsky.network",
    "jetstream.us-west.bsky.network",
    "jetstream1.us-east.bsky.network",
    "jetstream1.us-west.bsky.network",
    "jetstream2.us-east.bsky.network",
)
MAX_WINDOW_SECONDS = 5
MAX_CONNECT_SECONDS = 4.0
MAX_EVENTS = 10
SEARCH_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
SEARCH_QUERIES = (
    "breaking news",
    "new product",
    "technology",
    "product launch",
    "startup",
    "funding",
    "open source release",
    "research",
    "cybersecurity",
    "geopolitics",
    "energy",
    "health",
    "economy",
    "election",
    "climate",
    "space",
    "gaming",
    "music",
    "fashion",
)

_LOW_SIGNAL_PHRASES = (
    "thanks for listening", "thanks for watching", "good morning",
    "good night", "one more out", "yes!!!!!", "forever friends",
    "twitch.tv", "come watch", "follows and nerdy chat", "join me for chill",
    "voter guide", "drop off your ballot", "mail-in ballot",
    "i am again asking for your support",
)


def _websocket_url(host: str, *, start: datetime, end: datetime) -> str:
    if host.startswith("jetstream."):
        # v2 is the recommended public endpoint and supports time-cursor replay.
        # The short bounded sample keeps bandwidth and CPU low on local machines.
        query = urlencode(
            {
                "collections": "app.bsky.feed.post",
                "kinds": "commit",
                "cursor": int(start.timestamp() * 1_000_000),
            }
        )
        return urlunparse(
            (
                "wss",
                host,
                "/xrpc/network.bsky.jetstream.subscribeEvents",
                "",
                query,
                "",
            )
        )

    query = urlencode(
        {
            "wantedCollections": "app.bsky.feed.post",
            "start": int(start.timestamp() * 1_000_000),
            "end": int(end.timestamp() * 1_000_000),
        }
    )
    return urlunparse(("wss", host, "/subscribe", "", query, ""))


def _connect_timeout(remaining_seconds: float) -> float | None:
    """Never let sequential host failover exceed the sample's time budget."""
    if remaining_seconds <= 0:
        return None
    return min(MAX_CONNECT_SECONDS, remaining_seconds)


def _post_to_event(message: dict[str, Any]) -> RawEvent | None:
    payload = message.get("payload")
    if isinstance(payload, dict):
        # Jetstream v2 wraps typed records in a message envelope.
        if not str(payload.get("$type") or "").endswith("#commit"):
            return None
        commit = payload
    else:
        # Jetstream v1 compatibility.
        commit = message.get("commit") or {}
    if commit.get("collection") != "app.bsky.feed.post":
        return None
    if commit.get("operation") not in {"create", "update"}:
        return None

    record = commit.get("record") or {}
    text = str(record.get("text") or "").strip()
    did = str(commit.get("did") or message.get("did") or "")
    rkey = str(commit.get("rkey") or "")
    if not text or not did or not rkey:
        return None
    normalized = " ".join(text.casefold().split())
    # Jetstream is a firehose sample, not a trends endpoint. Reject empty
    # reactions, boilerplate, and non-informative posts before they hit storage.
    if len(normalized) < 55 or len(normalized.split()) < 9:
        return None
    if normalized in _LOW_SIGNAL_PHRASES:
        return None

    created = record.get("createdAt") or commit.get("time") or message.get("time")
    try:
        published = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        published = None

    handle = str(record.get("handle") or did)
    tags = re.findall(r"(?<!\w)#([\w-]+)", text, flags=re.UNICODE)
    # Jetstream is a random public-post sample, not a trend endpoint. Only keep
    # posts tied to the app's tracked topics; drop personal chatter and replies.
    from app.seed.tag_taxonomy import TAG_KEYWORDS

    searchable = f" {normalized} "
    relevant = {
        term.casefold()
        for terms in TAG_KEYWORDS.values()
        for term in terms
        if term and f" {term.casefold()} " in searchable
    }
    relevant.update(
        tag.casefold().replace("_", " ")
        for tag in tags
        if tag.casefold().replace("_", " ") in TAG_KEYWORDS
    )
    if not relevant:
        return None
    # Jetstream is an unranked firehose. Without engagement counters, a single
    # post cannot establish a trend; require multiple concrete topic matches.
    if len(relevant) < 2:
        return None
    if len(normalized.split()) < 14:
        return None
    if any(
        phrase in normalized
        for phrase in (
            "reply", "dm me", "sign up", "get started", "my shop",
            "buy now", "limited time", "use my code", "check out my",
        )
    ):
        return None
    # Personal or crisis posts are never useful trend signals; the stream is
    # sampled, unmoderated public chatter and has no engagement context.
    if any(
        phrase in normalized
        for phrase in (
            "kill myself", "end my life", "suicide", "self-harm",
            "i want to die", "no longer be alive",
        )
    ):
        return None
    return RawEvent(
        source_id="bluesky_stream",
        external_id=f"at://{did}/app.bsky.feed.post/{rkey}",
        title=text[:500],
        url=f"https://bsky.app/profile/{did}/post/{rkey}",
        description=text[:1800],
        activity=0.0,
        activity_metric="live_posts",
        category="social_post",
        hashtags=tags[:20],
        published_at=published,
        metadata={
            "author_did": did,
            "author_handle": handle,
            "cursor": commit.get("seq") or message.get("time_us"),
            "operation": commit.get("operation"),
            "strategy": "jetstream_live_sample",
            "sampled_stream": True,
            "matched_topics": sorted(relevant)[:8],
        },
    )


class BlueskyJetstreamStrategy(Strategy):
    name = "jetstream_live_sample"

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        del client  # Jetstream uses WebSocket, outside the shared HTTP pool.
        try:
            import websockets
        except ImportError as exc:
            raise SourceUnavailable("install websockets to enable Bluesky Jetstream") from exc

        now = datetime.now(UTC)
        start = now - timedelta(seconds=MAX_WINDOW_SECONDS)
        duration = min(
            max(int(ctx.extra.get("bluesky_sample_seconds", MAX_WINDOW_SECONDS)), 1),
            MAX_WINDOW_SECONDS,
        )
        deadline = asyncio.get_running_loop().time() + duration
        events: list[RawEvent] = []
        last_error: Exception | None = None

        for host in JETSTREAM_HOSTS:
            remaining = deadline - asyncio.get_running_loop().time()
            open_timeout = _connect_timeout(remaining)
            if open_timeout is None:
                break
            try:
                async with websockets.connect(
                    _websocket_url(host, start=start, end=now),
                    open_timeout=open_timeout,
                    close_timeout=1,
                    ping_interval=10,
                    max_size=1_048_576,
                ) as socket:
                    while len(events) < min(ctx.limit, MAX_EVENTS):
                        remaining = deadline - asyncio.get_running_loop().time()
                        if remaining <= 0:
                            break
                        try:
                            frame = await asyncio.wait_for(socket.recv(), timeout=remaining)
                        except asyncio.TimeoutError:
                            break
                        try:
                            message = json.loads(frame)
                        except (TypeError, json.JSONDecodeError):
                            continue
                        if isinstance(message, dict):
                            event = _post_to_event(message)
                            if event:
                                events.append(event)
                if events:
                    break
                raise SourceUnavailable("Bluesky Jetstream sample contained no topical posts")
            except SourceUnavailable:
                last_error = SourceUnavailable("Bluesky Jetstream sample contained no topical posts")
                continue
            except Exception as exc:
                last_error = exc
                logger.info("Bluesky Jetstream %s unavailable (%s)", host, type(exc).__name__)

        # Keep individually relevant posts, even when the short sample window
        # contains no second post on the same topic. Requiring repetition here
        # made a random 12-second firehose sample discard every early mention.
        # Preserve the evidence level explicitly so the UI/scoring path can
        # distinguish a single observation from a repeated topic.
        if events:
            return _annotate_topic_corroboration(events)[: min(ctx.limit, MAX_EVENTS)]

        if last_error:
            raise SourceUnavailable(
                "Bluesky Jetstream sample had no relevant posts; "
                f"last connection error: {type(last_error).__name__}"
            ) from last_error
        raise SourceUnavailable(
            "Bluesky Jetstream sample had no relevant posts"
        )


def _annotate_topic_corroboration(events: list[RawEvent]) -> list[RawEvent]:
    """Record repeated authors per topic without treating a short sample as confirmation."""
    authors_by_topic: dict[str, set[str]] = {}
    for event in events:
        author = str(event.metadata.get("author_did") or "").strip()
        if not author:
            continue
        for topic in event.metadata.get("matched_topics", []):
            authors_by_topic.setdefault(topic, set()).add(author)
    for event in events:
        topics = event.metadata.get("matched_topics", [])
        author_count = max(1, max(
            (len(authors_by_topic.get(topic, set())) for topic in topics),
            default=0,
        ))
        event.metadata["topic_sample_count"] = author_count
        event.metadata["topic_distinct_authors"] = author_count
        event.metadata["topic_repeated_in_sample"] = author_count >= 2
        # A 12-second slice of one network is not independent confirmation.
        # Cross-family evidence is computed later by the signal pipeline.
        event.metadata["topic_corroborated"] = False
    return events


class BlueskySearchStrategy(Strategy):
    """Search topical public posts and score their actual engagement."""

    name = "public_search_engagement"
    disabled_until = 0.0

    async def fetch(self, client: Any, ctx: FetchContext) -> list[RawEvent]:
        if time.monotonic() < self.disabled_until:
            raise SourceUnavailable(
                "Bluesky public search is cooling down after HTTP 403; "
                "using the bounded Jetstream fallback"
            )

        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=6)
        terms = [str(term).replace("-", " ").strip() for term in ctx.keywords]
        terms = [term for term in terms if len(term) >= 3]
        query_pool = list(dict.fromkeys(terms)) if terms else list(SEARCH_QUERIES)
        cycle = int(now.timestamp() // 600)
        start = (cycle * 3) % len(query_pool)
        queries = [query_pool[(start + i) % len(query_pool)] for i in range(min(3, len(query_pool)))]

        import asyncio

        responses = await asyncio.gather(
            *(
                client.get_json(
                    SEARCH_URL,
                    params={
                        "q": query,
                        "sort": "latest",
                        "limit": min(max(ctx.limit, 1), 25),
                    },
                    retries=1,
                )
                for query in queries
            ),
            return_exceptions=True,
        )

        events: list[RawEvent] = []
        seen: set[str] = set()
        failure_messages: list[str] = []
        for query, payload in zip(queries, responses, strict=True):
            if isinstance(payload, BaseException):
                failure_messages.append(str(payload))
                continue
            posts = payload.get("posts", []) if isinstance(payload, dict) else []
            if not isinstance(posts, list):
                continue
            for post in posts:
                if not isinstance(post, dict):
                    continue
                record = post.get("record") or {}
                text = str(record.get("text") or "").strip()
                uri = str(post.get("uri") or "")
                author = post.get("author") or {}
                did = str(author.get("did") or "")
                handle = str(author.get("handle") or did)
                if len(text) < 40 or not uri or uri in seen:
                    continue

                created = record.get("createdAt") or post.get("indexedAt")
                try:
                    published = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                    if published.tzinfo is None:
                        published = published.replace(tzinfo=UTC)
                    published = published.astimezone(UTC)
                except (TypeError, ValueError):
                    published = None
                if published and published < cutoff:
                    continue

                likes = _safe_count(post.get("likeCount"))
                reposts = _safe_count(post.get("repostCount"))
                replies = _safe_count(post.get("replyCount"))
                quotes = _safe_count(post.get("quoteCount"))
                activity = likes + reposts * 2 + replies * 1.5 + quotes * 2
                if record.get("reply") and activity < 5:
                    continue
                rkey = uri.rsplit("/", 1)[-1]
                seen.add(uri)
                events.append(
                    RawEvent(
                        source_id="bluesky_stream",
                        external_id=uri,
                        title=text[:500],
                        url=f"https://bsky.app/profile/{handle}/post/{rkey}",
                        description=text[:1800],
                        activity=activity,
                        activity_metric="social_engagement",
                        category="social_post",
                        hashtags=re.findall(r"(?<!\w)#([\w-]+)", text, flags=re.UNICODE)[:20],
                        published_at=published,
                        metadata={
                            "author_did": did,
                            "author_handle": handle,
                            "query": query,
                            "likes": likes,
                            "reposts": reposts,
                            "replies": replies,
                            "quotes": quotes,
                            "strategy": self.name,
                        },
                    )
                )
                if len(events) >= min(ctx.limit, MAX_EVENTS * 2):
                    return events

        if not events:
            if any("HTTP 403" in message for message in failure_messages):
                # This is a public endpoint, so a 403 is a network/service access
                # block rather than an empty search result. Avoid repeating three
                # futile requests every pass; Jetstream remains the live fallback.
                self.disabled_until = time.monotonic() + 3600
                raise SourceUnavailable(
                    "Bluesky public search returned HTTP 403; paused for 1 hour"
                )
            detail = (
                ", ".join(sorted({type(response).__name__ for response in responses}))
                if failure_messages
                else "no matching recent posts"
            )
            raise SourceUnavailable(f"Bluesky public search unavailable: {detail}")
        return events


def _safe_count(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


@register_source
class BlueskyJetstreamAdapter(SourceAdapter):
    source_id = "bluesky_stream"
    name = "Bluesky Live Stream"
    type = SourceType.SOCIAL
    description = (
        "Topic search ranked by public likes, reposts, replies and quotes, with "
        "a bounded Jetstream fallback. No login required."
    )
    capabilities = ["live_stream", "social", "microblogging", "hashtags"]
    priority = 15
    cost = "FREE"
    credentials_required = False
    collect_interval_seconds = 600
    # Search returns ranked posts with engagement metrics. The v2 live sample
    # remains a bounded fallback for fresh posts the search index hasn't caught.
    strategies = [BlueskySearchStrategy(), BlueskyJetstreamStrategy()]

    async def fetch(self, ctx: FetchContext, client: Any) -> FetchResult:
        return await run_strategy_cascade(self, ctx, client)
