from types import SimpleNamespace

from app.core.config import settings
from app.pipeline.collectors.base import FetchResult
from app.services.pipeline_service import (
    _next_source_delay,
    run_collection_cycle,
)


def test_failed_slow_source_retries_before_its_normal_hourly_cadence(monkeypatch):
    source = SimpleNamespace(source_id="retry-test", collect_interval_seconds=3600)
    failed = FetchResult(
        source_id=source.source_id,
        events=[],
        strategy="none",
        ok=False,
        error="temporary network failure",
    )
    healthy_empty = FetchResult(
        source_id=source.source_id,
        events=[],
        strategy="none",
        ok=True,
        notes="no new events",
    )
    monkeypatch.setattr(settings, "collect_interval_seconds", 60)
    monkeypatch.setattr(settings, "source_cooldown_seconds", 300)
    monkeypatch.setattr(run_collection_cycle, "_source_failures", {}, raising=False)

    assert _next_source_delay(source, failed) == 300
    assert _next_source_delay(source, failed) == 600
    assert _next_source_delay(source, healthy_empty) == 3600
    assert run_collection_cycle._source_failures == {}


def test_rate_limited_source_uses_long_backoff(monkeypatch):
    source = SimpleNamespace(source_id="rate-limit-test", collect_interval_seconds=3600)
    rate_limited = FetchResult(
        source_id=source.source_id,
        events=[],
        strategy="none",
        ok=False,
        error="HTTP 429 from public endpoint",
    )
    monkeypatch.setattr(settings, "collect_interval_seconds", 60)
    monkeypatch.setattr(run_collection_cycle, "_source_failures", {}, raising=False)

    assert _next_source_delay(source, rate_limited) == 3600
    assert _next_source_delay(source, rate_limited) == 3600
