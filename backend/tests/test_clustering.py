"""Tests for EventClusterer cross-source grouping engine."""

from __future__ import annotations

import pytest
from app.pipeline.clustering import EventClusterer, extract_primary_entity


def test_extract_primary_entity():
    assert "comfyui" in extract_primary_entity("ComfyUI v1.0 Released for Diffusion Models")
    assert "claude" in extract_primary_entity("Introducing Claude Code by Anthropic")


def test_clusterer_groups_same_topic():
    clusterer = EventClusterer()
    
    key1, count1 = clusterer.add_event("github", "ComfyUI Local Diffusion Engine", {"id": 1})
    key2, count2 = clusterer.add_event("hackernews", "Show HN: ComfyUI fast backend", {"id": 2})
    
    assert key1 == key2
    assert count2 == 2  # 2 distinct sources (github, hackernews)


def test_clusterer_bounded_size():
    clusterer = EventClusterer(maxsize=2)
    clusterer.add_event("src1", "Alpha project release", {})
    clusterer.add_event("src2", "Beta framework update", {})
    clusterer.add_event("src3", "Gamma tool launched", {})
    
    assert clusterer.size <= 2
