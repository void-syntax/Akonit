from datetime import UTC, datetime, timedelta

from app.services.pipeline_service import _effective_event_time, aware


def test_aware_converts_offset_timestamps_to_utc_before_sqlite_storage():
    tokyo = datetime.fromisoformat("2026-10-29T11:53:24+09:00")

    assert aware(tokyo) == datetime(2026, 10, 29, 2, 53, 24, tzinfo=UTC)


def test_effective_event_time_clamps_future_publication_to_observation():
    observed = datetime(2026, 10, 29, 3, tzinfo=UTC)
    published = observed + timedelta(hours=6)

    assert _effective_event_time(published, observed) == observed
