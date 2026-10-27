"""Tests for Locality-Sensitive Hashing (LSH) Forest Index."""

from __future__ import annotations

import pytest
from app.core.lsh_forest import LSHForestIndex, get_lsh_forest


def test_lsh_forest_indexing_and_query():
    forest = LSHForestIndex(num_tables=4, hash_bits=4)
    v1 = [1, 1, 0, 0, 1]
    v2 = [1, 1, 0, 0, 1]
    v3 = [0, 0, 1, 1, 0]

    forest.add("doc1", v1)
    forest.add("doc2", v2)
    forest.add("doc3", v3)

    results = forest.query_approximate(v1)
    assert "doc1" in results
    assert "doc2" in results


def test_lsh_forest_singleton():
    engine = get_lsh_forest()
    assert "lsh_forest" in engine
