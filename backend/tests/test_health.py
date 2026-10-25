"""Tests for CollectorHealthMonitor resilience tracking."""

from __future__ import annotations

import pytest
from app.pipeline.health import CollectorHealthMonitor


def test_health_monitor_report():
    monitor = CollectorHealthMonitor()
    report = monitor.health_report()
    assert report["total_monitored"] > 0
    assert report["tripped_circuits"] == 0
    assert "github" in report["breakers"]
