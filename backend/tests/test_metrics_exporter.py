"""Tests for pipeline metrics exporter."""

from __future__ import annotations

import pytest
from app.pipeline.metrics_exporter import export_pipeline_metrics


def test_export_pipeline_metrics():
    metrics = export_pipeline_metrics()
    assert "collector_health" in metrics
    assert metrics["system_status"] == "optimal"
