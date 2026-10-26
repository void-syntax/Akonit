"""Tests for StoryClusterer cross-source story synthesis engine."""

from __future__ import annotations

import pytest
from app.pipeline.story_clustering import StoryClusterer


def test_story_clusterer_merging():
    clusterer = StoryClusterer(max_clusters=100)
    
    c1 = clusterer.ingest_signal("New Open Source AI Agent Framework Released", "github", "https://github.com/test/agent", 0.8)
    c2 = clusterer.ingest_signal("Open Source AI Agent Framework Released Today", "hackernews", "https://news.ycombinator.com/item?id=1", 0.9)
    
    assert c1 == c2
    story = clusterer.get_cluster(c1)
    assert story is not None
    assert story["cross_source_count"] == 2
    assert "github" in story["sources"]
    assert "hackernews" in story["sources"]
    assert story["strength"] == 0.9
