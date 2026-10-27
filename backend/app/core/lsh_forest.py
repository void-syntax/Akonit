"""Locality-Sensitive Hashing (LSH) Forest & Approximate Nearest Neighbor Index (`backend/app/core/lsh_forest.py`).

Provides memory-efficient sub-linear approximate nearest neighbor search and multi-bucket indexing
for high-speed signal deduplication and semantic vector-less clustering.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any
from app.core.logging import get_logger

logger = get_logger("app.core.lsh_forest")


class LSHForestIndex:
    """Memory-efficient Locality-Sensitive Hashing Forest for approximate similarity lookup."""

    def __init__(self, num_tables: int = 4, hash_bits: int = 8) -> None:
        self.num_tables = num_tables
        self.hash_bits = hash_bits
        self.tables: list[dict[str, list[str]]] = [defaultdict(list) for _ in range(num_tables)]
        self.documents: dict[str, list[int]] = {}

    def _hash_vector(self, vec: list[int], table_idx: int) -> str:
        # Simple random hyperplane simulation hashing based on vector elements
        bits = []
        for b in range(self.hash_bits):
            val = vec[(b + table_idx) % len(vec)] if vec else 0
            bits.append("1" if val > 0 else "0")
        return "".join(bits)

    def add(self, doc_id: str, vector: list[int]) -> None:
        self.documents[doc_id] = vector
        for t_idx in range(self.num_tables):
            h_key = self._hash_vector(vector, t_idx)
            self.tables[t_idx][h_key].append(doc_id)

    def query_approximate(self, vector: list[int], max_results: int = 5) -> list[str]:
        candidates: set[str] = set()
        for t_idx in range(self.num_tables):
            h_key = self._hash_vector(vector, t_idx)
            if h_key in self.tables[t_idx]:
                for doc_id in self.tables[t_idx][h_key]:
                    candidates.add(doc_id)
        return list(candidates)[:max_results]


_lsh_forest = LSHForestIndex()


def get_lsh_forest() -> dict[str, Any]:
    return {"lsh_forest": _lsh_forest}
