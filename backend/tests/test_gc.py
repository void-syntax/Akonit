"""Tests for memory garbage collection module."""

from __future__ import annotations

import pytest
from app.core.gc import run_aggressive_garbage_collection


def test_aggressive_garbage_collection():
    stats = run_aggressive_garbage_collection()
    assert "collected_objects" in stats
    assert isinstance(stats["collected_objects"], int)
