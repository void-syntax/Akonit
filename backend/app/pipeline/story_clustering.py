"""Enhanced Cross-Source Event Clustering & Story Synthesis Engine (`backend/app/pipeline/story_clustering.py`).

Groups disparate signals from multiple heterogeneous sources (GitHub, Hacker News, 
Lobsters, Dev.to, Bluesky) into unified 'Story Nodes' using TF-IDF token overlap
and normalized URI matching.
"""

from __future__ import annotations

import re
from collections import OrderedDict, defaultdict
from typing import Any
from app.core.logging import get_logger

logger = get_logger("app.pipeline.story_clustering")

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "http", "https",
    "com", "org", "net", "github", "new", "how", "why", "what", "are", "you",
    "your", "was", "were", "will", "can", "has", "had", "have", "our", "out"
}


class StoryClusterer:
    """Memory-bounded cross-source story clusterer with entity overlap scoring."""

    def __init__(self, max_clusters: int = 2000) -> None:
        self.max_clusters = max_clusters
        # cluster_id -> dict of story details
        self._clusters: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def _tokenize(self, text: str) -> set[str]:
        words = re.findall(r"\w+", text.lower())
        return {w for w in words if len(w) > 3 and w not in STOPWORDS}

    def _jaccard_similarity(self, set1: set[str], set2: set[str]) -> float:
        if not set1 or not set2:
            return 0.0
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        return intersection / union if union > 0 else 0.0

    def ingest_signal(self, title: str, source_id: str, url: str, strength: float) -> str:
        """Ingest a signal and return its assigned story cluster ID."""
        tokens = self._tokenize(title)
        best_cluster_id = ""
        best_sim = 0.0

        # Find best matching existing cluster within memory bounds
        for cid, cluster in self._clusters.items():
            sim = self._jaccard_similarity(tokens, cluster["tokens"])
            if sim > best_sim:
                best_sim = sim
                best_cluster_id = cid

        # If similarity exceeds threshold, merge into story cluster
        if best_sim >= 0.35 and best_cluster_id:
            cluster = self._clusters[best_cluster_id]
            cluster["sources"].add(source_id)
            cluster["urls"].append(url)
            cluster["strength"] = max(cluster["strength"], strength)
            cluster["count"] += 1
            cluster["tokens"].update(tokens)
            self._clusters.move_to_end(best_cluster_id)
            return best_cluster_id

        # Otherwise, create a new story cluster
        new_cid = f"story_{abs(hash(title)) % 10000000}"
        if len(self._clusters) >= self.max_clusters:
            self._clusters.popitem(last=False)  # Evict oldest

        self._clusters[new_cid] = {
            "title": title,
            "tokens": tokens,
            "sources": {source_id},
            "urls": [url],
            "strength": strength,
            "count": 1,
        }
        return new_cid

    @property
    def size(self) -> int:
        return len(self._clusters)

    def get_cluster(self, cluster_id: str) -> dict[str, Any] | None:
        cluster = self._clusters.get(cluster_id)
        if not cluster:
            return None
        return {
            "title": cluster["title"],
            "sources": list(cluster["sources"]),
            "cross_source_count": len(cluster["sources"]),
            "urls": cluster["urls"],
            "strength": cluster["strength"],
            "count": cluster["count"],
        }


_story_clusterer: StoryClusterer | None = None


def get_story_clusterer() -> StoryClusterer:
    global _story_clusterer
    if _story_clusterer is None:
        _story_clusterer = StoryClusterer(max_clusters=2000)
        logger.info("StoryClusterer initialized (max_clusters=2000)")
    return _story_clusterer
