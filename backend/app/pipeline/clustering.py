"""Lightweight Cross-Source Event Clustering Engine (`backend/app/pipeline/clustering.py`).

Группирует события из разных источников (GitHub, HN, Reddit, Mastodon, YouTube),
которые относятся к одной и той же теме или проекту, в единые кластеры
для автоматического подтверждения (cross-source corroboration) без тяжелых LLM.

Работает за O(1) на основе нормализованных ключевых сущностей и заголовков.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

from app.core.logging import get_logger

logger = get_logger("app.pipeline.clustering")

_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "new", "released",
    "release", "update", "how", "why", "what", "to", "in", "on", "is", "are",
    "an", "a", "by", "at", "as", "it", "its", "our", "we", "you", "your",
    "show", "hn", "ask", "tell", "launching", "launched", "project", "tool",
    "introducing", "announcing", "custom", "best", "top",
}


def extract_primary_entity(title: str) -> str:
    """Extract the primary noun/project name or keyword from a title string."""
    cleaned = re.sub(r"[^\w\s]", "", title.lower())
    words = [w for w in cleaned.split() if w not in _STOPWORDS and len(w) > 2]
    if not words:
        return cleaned[:30]
    return words[0]


class EventClusterer:
    """Memory-bounded cross-source event clustering engine.

    Groups incoming events by primary entity and tracks participating sources.
    """

    def __init__(self, maxsize: int = 5000) -> None:
        self.maxsize = maxsize
        self._clusters: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def add_event(self, source_id: str, title: str, event_data: dict[str, Any]) -> tuple[str, int]:
        """Add an event to its corresponding entity cluster.

        Returns:
            (entity_key, cross_source_count)
        """
        entity_key = extract_primary_entity(title)
        if not entity_key:
            entity_key = "general_trend"

        if entity_key in self._clusters:
            cluster = self._clusters[entity_key]
            cluster["sources"].add(source_id)
            cluster["events"].append({"source_id": source_id, "title": title, **event_data})
            self._clusters.move_to_end(entity_key)
        else:
            if len(self._clusters) >= self.maxsize:
                self._clusters.popitem(last=False)
            self._clusters[entity_key] = {
                "sources": {source_id},
                "events": [{"source_id": source_id, "title": title, **event_data}],
            }

        cluster = self._clusters[entity_key]
        cross_count = len(cluster["sources"])
        return entity_key, cross_count

    def get_cluster(self, entity_key: str) -> dict[str, Any] | None:
        return self._clusters.get(entity_key)

    @property
    def size(self) -> int:
        return len(self._clusters)

    def clear(self) -> None:
        self._clusters.clear()


_clusterer: EventClusterer | None = None


def get_clusterer() -> EventClusterer:
    global _clusterer
    if _clusterer is None:
        _clusterer = EventClusterer()
        logger.info("EventClusterer initialized (maxsize=5000)")
    return _clusterer
