"""Deduplication layer.

One topic appearing on TikTok, YouTube, Reddit and GitHub must not create four
identical signals, yet merging must stay conservative: unrelated objects should
never collapse together. Two signals cluster when BOTH the URL matches exactly
OR their content fingerprints are close enough in simhash space and recent.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.pipeline.normalization.normalizer import canonicalize_url, similarity, simhash


@dataclass
class ClusterCandidate:
    cluster_id: str
    source_id: str
    url: str
    simhash: int
    observed_at: float


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
) -> DedupDecision:
    """Return the cluster this event belongs to."""
    window = (
        window_minutes
        if window_minutes is not None
        else settings.detect_dedup_window_minutes
    )
    own_canonical = canonicalize_url(url)
    own_hash = simhash(f"{title} {description}")

    exact_url: ClusterCandidate | None = None
    best: tuple[float, ClusterCandidate] | None = None

    for candidate in candidates:
        if candidate.source_id == source_id and canonicalize_url(candidate.url) == own_canonical:
            exact_url = candidate
            break

        score = similarity(own_hash, candidate.simhash)
        if score > settings.dedup_similarity_threshold and (
            best is None or score > best[0]
        ):
            best = (score, candidate)

    if exact_url:
        return DedupDecision(exact_url.cluster_id, False, "exact_url", 1.0)

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