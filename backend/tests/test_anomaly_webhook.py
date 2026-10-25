"""Tests for anomaly webhook dispatcher."""

from __future__ import annotations

import pytest
from app.notifications.anomaly_webhook import dispatch_anomaly_alert


@pytest.mark.asyncio
async def test_dispatch_anomaly_alert_empty_url():
    success = await dispatch_anomaly_alert("", "AI Trend", 0.95)
    assert success is False
