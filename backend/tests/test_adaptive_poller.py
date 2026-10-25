"""Tests for AdaptivePollingController module."""

from __future__ import annotations

import pytest
from app.pipeline.adaptive_poller import AdaptivePollingController


def test_adaptive_poller():
    poller = AdaptivePollingController(base_interval=60.0)
    
    i1 = poller.get_interval("github")
    assert i1 == 60.0

    # High velocity should speed up (decrease interval)
    i2 = poller.adapt("github", high_velocity=True)
    assert i2 < 60.0

    # Low velocity should slow down (increase interval)
    i3 = poller.adapt("github", high_velocity=False)
    assert i3 > i2
