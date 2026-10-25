"""Vector similarity search & hybrid search engine module using hnswlib / numpy.
Provides in-memory vector embedding similarity search for signals and trends.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.logging import get_logger

logger = get_logger("app.core.vector_search")

try:
    import numpy as np
    import hnswlib
    HAS_VECTOR_ENGINE = True
except ImportError:
    HAS_VECTOR_ENGINE = False


class VectorSearchEngine:
    """Lightweight in-process HNSW vector search engine for semantic signal retrieval."""

    def __init__(self, dim: int = 384, max_elements: int = 10000) -> None:
        self.dim = dim
        self.max_elements = max_elements
        self.index: Any | None = None
        self.id_mapping: dict[int, str] = {}
        self.next_label = 0

        if HAS_VECTOR_ENGINE:
            try:
                self.index = hnswlib.Index(space="cosine", dim=self.dim)
                self.index.init_index(max_elements=self.max_elements, ef_construction=200, M=16)
                self.index.set_ef(50)
                logger.info("VectorSearchEngine initialized successfully (dim=%d)", dim)
            except Exception as exc:
                logger.warning("Failed to initialize hnswlib index: %s", exc)
                self.index = None

    def add_item(self, external_id: str, vector: list[float] | Any) -> None:
        if self.index is None:
            return
        try:
            vec = np.array(vector, dtype=np.float32)
            if vec.shape[0] != self.dim:
                return
            label = self.next_label
            self.index.add_items(vec.reshape(1, -1), np.array([label]))
            self.id_mapping[label] = external_id
            self.next_label += 1
            if self.next_label >= self.max_elements:
                # Resize if needed
                self.index.resize_index(self.max_elements * 2)
                self.max_elements *= 2
        except Exception as exc:
            logger.debug("vector add failed: %s", exc)

    def query(self, vector: list[float] | Any, k: int = 5) -> list[tuple[str, float]]:
        if self.index is None or self.next_label == 0:
            return []
        try:
            vec = np.array(vector, dtype=np.float32)
            labels, distances = self.index.knn_query(vec.reshape(1, -1), k=min(k, self.next_label))
            results = []
            for label, dist in zip(labels[0], distances[0]):
                ext_id = self.id_mapping.get(int(label))
                if ext_id is not None:
                    # distance is cosine distance (1 - similarity), similarity = 1 - dist
                    similarity = float(1.0 - dist)
                    results.append((ext_id, similarity))
            return results
        except Exception as exc:
            logger.debug("vector query failed: %s", exc)
            return []


# Global vector search singleton instance
_vector_engine = VectorSearchEngine()

def get_vector_engine() -> VectorSearchEngine:
    return _vector_engine
