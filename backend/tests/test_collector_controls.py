from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.pipeline.collectors.base import RawEvent
from app.schemas.api import ProfileUpdate
from app.services.pipeline_service import (
    _matches_collection_keywords,
    _weighted_source_delay,
)


def test_source_weight_scales_poll_frequency_and_handles_bounds():
    assert _weighted_source_delay(600, 10) == 300
    assert _weighted_source_delay(600, 5) == 600
    assert _weighted_source_delay(600, 1) == 3000
    assert _weighted_source_delay(600, 99) == 300


def test_profile_collector_settings_validate_and_clean_keywords():
    result = ProfileUpdate.model_validate(
        {
            "collector_source_weights": {"x_trends": 10, "reddit": 0},
            "collector_keywords": ["  battery breakthrough ", "battery breakthrough"],
        }
    )
    assert result.collector_source_weights == {"x_trends": 10, "reddit": 0}
    assert result.collector_keywords == ["battery breakthrough"]

    with pytest.raises(ValidationError):
        ProfileUpdate.model_validate({"collector_source_weights": {"x_trends": 11}})


def test_keyword_focus_requires_a_phrase_match_in_event_text_or_hashtag():
    event = RawEvent(
        source_id="test",
        external_id="1",
        title="New solid state battery announced",
        url="https://example.com",
    )
    assert _matches_collection_keywords(event, ["solid state battery"])
    assert not _matches_collection_keywords(event, ["AI agents"])
    event.description = "An unrelated snippet mentions AI agents in passing."
    assert not _matches_collection_keywords(event, ["AI agents"])
    event.hashtags = ["BatteryTech"]
    assert _matches_collection_keywords(event, ["batterytech"])
