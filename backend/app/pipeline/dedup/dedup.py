"""Deduplication layer.

One topic appearing on TikTok, YouTube, Reddit and GitHub must not create four
identical signals, yet merging must stay conservative: unrelated objects should
never collapse together. Two signals cluster when BOTH the URL matches exactly
OR their content fingerprints are close enough in simhash space and recent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

from app.core.config import settings
from app.pipeline.normalization.normalizer import (
    canonicalize_url,
    normalize_text,
    similarity,
    simhash,
)


@dataclass
class ClusterCandidate:
    cluster_id: str
    source_id: str
    url: str
    simhash: int
    observed_at: float
    title: str = ""
    external_id: str = ""
    canonical_url: str = field(init=False)
    normalized_title: str = field(init=False)

    def __post_init__(self) -> None:
        # Candidates are compared against many events per cycle. Parse and
        # normalize each candidate URL once instead of once per comparison.
        self.canonical_url = canonicalize_url(self.url)
        self.normalized_title = normalize_text(self.title)


@dataclass
class DedupDecision:
    cluster_id: str
    is_new_cluster: bool
    reason: str
    similarity: float = 0.0


def make_cluster_id(url: str, source_id: str, external_id: str) -> str:
    """Deterministic id so the same entity always lands in the same cluster."""
    canonical = canonicalize_url(url) or f"{source_id}:{external_id}"
    return f"{source_id}:{external_id}" if not canonical else canonical


def find_cluster(
    title: str,
    description: str,
    url: str,
    source_id: str,
    external_id: str,
    candidates: list[ClusterCandidate],
    *,
    window_minutes: int | None = None,
    content_fingerprint: int | None = None,
) -> DedupDecision:
    """Return the cluster this event belongs to."""
    window = (
        window_minutes
        if window_minutes is not None
        else settings.detect_dedup_window_minutes
    )
    own_canonical = canonicalize_url(url)
    own_hash = (
        content_fingerprint
        if content_fingerprint is not None
        else simhash(f"{title} {description}")
    )
    own_title = normalize_text(title)

    exact_url: ClusterCandidate | None = None
    exact_title: ClusterCandidate | None = None
    best: tuple[float, ClusterCandidate] | None = None
    now_ts = datetime.now(UTC).timestamp()
    cutoff = now_ts - window * 60

    for candidate in candidates:
        if candidate.observed_at < cutoff or candidate.observed_at > now_ts + 300:
            continue

        if _same_canonical_url(
            own_canonical,
            candidate.canonical_url,
            source_a=source_id,
            source_b=candidate.source_id,
        ):
            exact_url = candidate
            break

        # A stable, sufficiently descriptive title from the same source is a
        # cheap idempotency key even when that source changes its permalink or
        # accompanying summary between fetches. Keep cross-source matching on
        # the stricter content fingerprint path below.
        if (
            source_id == candidate.source_id
            and len(own_title) >= 24
            and own_title == candidate.normalized_title
        ):
            exact_title = candidate
            break

        score = similarity(own_hash, candidate.simhash)
        if should_merge_cross_source(source_id, candidate.source_id, score) and (
            best is None or score > best[0]
        ):
            best = (score, candidate)

    if exact_url:
        return DedupDecision(exact_url.cluster_id, False, "exact_url", 1.0)

    if exact_title:
        return DedupDecision(exact_title.cluster_id, False, "same_source_title", 1.0)

    if best:
        score, candidate = best
        return DedupDecision(
            candidate.cluster_id,
            False,
            "similar_content",
            score,
        )

    cluster_id = make_cluster_id(url, source_id, external_id)
    return DedupDecision(cluster_id, True, "new_cluster", 0.0)


def _same_canonical_url(
    url_a: str,
    url_b: str,
    *,
    source_a: str,
    source_b: str,
) -> bool:
    """Match equivalent URLs without merging unrelated source pages.

    Exact URL matching is valuable for syndication, but path-only or hostless
    URLs are ambiguous (e.g. every service can have `/status`). Require an
    explicit hostname across sources. Same-source adapters may still emit a
    canonical relative URL when that is all the source provides.
    """
    if not url_a or url_a != url_b:
        return False
    parsed = urlparse(url_a)
    if source_a != source_b and not parsed.hostname:
        return False
    return True


def should_merge_cross_source(
    source_a: str,
    source_b: str,
    score: float,
    *,
    min_score: float | None = None,
) -> bool:
    """Cross-source merging needs a stricter bar than same-source matching."""
    threshold = (
        min_score if min_score is not None else settings.dedup_similarity_threshold
    )
    if source_a == source_b:
        return score >= threshold
    return score >= min(0.95, threshold + 0.1)
