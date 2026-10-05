"""Unit tests for the detection engine (scoring, lifecycle, metrics)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.models.enums import SignalStatus
from app.pipeline.detection.lifecycle import classify, is_actionable
from app.pipeline.detection.metrics import (
    ActivityPoint,
    compute_growth_acceleration,
    safe_pct,
)
from app.pipeline.detection.scoring import compute_strength
from app.services.pipeline_service import _is_stale

NOW = datetime.now(UTC)


def points(values: list[float], minutes: int = 15) -> list:
    """Build a chronological series: the LAST value is the newest observation."""
    from app.pipeline.detection.metrics import ActivityPoint

    return [
        ActivityPoint(
            captured_at=NOW - timedelta(minutes=minutes * (len(values) - 1 - i)),
            activity=value,
        )
        for i, value in enumerate(values)
    ]


class TestMetrics:
    def test_growth_without_a_baseline_is_zero(self):
        """A first sighting has nothing to compare against.

        Reporting 100% here made every newly discovered signal look like it was
        surging, which flooded the feed with identical RISING items.
        """
        assert safe_pct(100, 0) == 0.0
        assert safe_pct(0, 0) == 0.0

    def test_first_measurement_is_flagged_separately(self):
        """An item that only now started reporting a count is worth knowing."""
        first = compute_growth_acceleration(points([0, 500]), now=NOW)
        assert first.first_measurement
        assert not first.has_baseline
        # It is genuinely new, but it has not grown relative to anything.
        assert first.growth == 0.0

        seen = compute_growth_acceleration(points([500, 900]), now=NOW)
        assert seen.has_baseline
        assert not seen.first_measurement
        assert seen.growth == 80.0

    def test_unmeasured_samples_cannot_fake_momentum(self):
        """A feed that reports no numbers must not look like it is surging."""
        metrics = compute_growth_acceleration(points([0, 0, 0]), now=NOW)
        assert metrics.growth == 0.0
        assert metrics.velocity == 0.0
        assert metrics.persistence == 0

    def test_growth_percentage(self):
        assert safe_pct(200, 100) == 100.0
        assert safe_pct(50, 100) == -50.0

    def test_acceleration_needs_three_points(self):
        """Acceleration is the change of growth, so it needs a third point."""
        two = compute_growth_acceleration(points([100, 200]), now=NOW)
        assert not two.has_acceleration

        three = compute_growth_acceleration(points([100, 200, 400]), now=NOW)
        assert three.has_acceleration
        # growth: 100->200 = +100%, 200->400 = +100% => acceleration 0
        assert three.acceleration == 0.0

        accelerating = compute_growth_acceleration(
            points([100, 200, 800]), now=NOW
        )
        # growth: +100% then +300% => acceleration +200
        assert accelerating.acceleration == 200.0

    def test_persistence_counts_growing_windows(self):
        metrics = compute_growth_acceleration(points([10, 20, 40, 80]), now=NOW)
        assert metrics.persistence == 3


class TestFreshnessFilter:
    """Ingestion must reject evergreen items that look new.

    Search-driven collectors keep returning the same old, highly-viewed hits.
    Without a publication-date cutoff those enter the feed looking like breaking
    news, which is the single loudest source of noise in the product.
    """

    def test_rejects_old_publication(self) -> None:
        old = datetime(2020, 1, 1, tzinfo=UTC)
        assert _is_stale(old) is True

    def test_keeps_recent_publication(self) -> None:
        assert _is_stale(datetime.now(UTC) - timedelta(hours=2)) is False

    def test_boundary_is_configurable(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "detect_max_age_hours", 0)
        assert _is_stale(datetime(1990, 1, 1, tzinfo=UTC)) is False


class TestTagFiltering:
    """The feed filters by tag, and the reported total must agree.

    Tag filtering used to happen in Python after the query, so `total` counted
    every signal while `items` held only the matches. A user selecting a tag saw
    "12 found" above a list of two.
    """

    @staticmethod
    def _client_session(tmp_path, monkeypatch):
        import asyncio

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.db.session import Base
        from app.models import Signal  # noqa: F401  (registers the table)
        from app.models.enums import SignalStatus

        db = tmp_path / "tags.db"
        url = f"sqlite+aiosqlite:///{db.as_posix()}"
        engine = create_async_engine(url)
        session = async_sessionmaker(engine, expire_on_commit=False)

        async def setup() -> None:
            from datetime import datetime, timezone

            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            now = datetime.now(timezone.utc)
            async with session() as s:
                for sid, kw in [
                    ("s1", ["makeup", "beauty"]),
                    ("s2", ["ai-agents"]),
                    ("s3", ["tiktok-memes"]),
                    ("s4", ["beauty"]),
                ]:
                    s.add(
                        Signal(
                            id=sid,
                            cluster_id=sid,
                            title=sid,
                            slug=sid,
                            description="",
                            hashtags=[],
                            source_id="tiktok",
                            source_url=f"http://x/{sid}",
                            first_seen_at=now,
                            last_seen_at=now,
                            current_activity=10,
                            previous_activity=0,
                            status=SignalStatus.NEW,
                            strength=50.0,
                            keywords=kw,
                        )
                    )
                await s.commit()

        return setup, session, engine

    def test_total_matches_items(self, tmp_path, monkeypatch) -> None:
        import asyncio

        setup, session, engine = self._client_session(tmp_path, monkeypatch)
        asyncio.run(setup())

        try:
            from app.api.v1.signals import list_signals

            async def query(tags):
                async with session() as s:
                    # Called through the ASGI app so FastAPI supplies the
                    # defaults the route expects when invoked outside a request.
                    page = await list_signals(
                        session=s,
                        user=None,
                        status_filter=None,
                        tab="all",
                        country=None,
                        source=None,
                        radar_id=None,
                        tag=tags,
                        keyword=None,
                        min_strength=None,
                        max_age_minutes=None,
                        limit=30,
                        offset=0,
                    )
                    return page.total, [i.title for i in page.items]

            total, items = asyncio.run(query(["makeup"]))
            assert total == len(items) == 1

            # Multiple tags behave as OR.
            total, items = asyncio.run(query(["makeup", "ai-agents"]))
            assert total == len(items) == 2

            total, items = asyncio.run(query(["nope"]))
            assert total == len(items) == 0
        finally:
            asyncio.run(engine.dispose())


class TestScoring:
    def test_popular_but_flat_scores_lower_than_sharp_rise(self):
        """The core product rule: POPULAR != RISING."""
        flat = compute_growth_acceleration(points([50000, 50000, 50000]), now=NOW)
        sharp = compute_growth_acceleration(
            points([10, 40, 400, 1600]), now=NOW
        )

        flat_strength = compute_strength(flat)
        sharp_strength = compute_strength(sharp)

        assert sharp_strength > flat_strength, (
            f"sharp={sharp_strength} should beat flat={flat_strength}"
        )

    def test_old_flat_object_is_penalised(self):
        old_points = [
            ActivityPoint(
                captured_at=NOW - timedelta(hours=72), activity=100000
            ),
            ActivityPoint(
                captured_at=NOW - timedelta(hours=48), activity=100000
            ),
            ActivityPoint(
                captured_at=NOW - timedelta(hours=24), activity=100000
            ),
        ]
        old_flat = compute_growth_acceleration(old_points, now=NOW)
        fresh_sharp = compute_growth_acceleration(
            points([10, 50, 500, 3000]), now=NOW
        )
        assert compute_strength(fresh_sharp) > compute_strength(old_flat)

    def test_strength_within_bounds(self):
        for values in ([0], [1, 1], [1, 1000], [5, 5, 5, 5]):
            metrics = compute_growth_acceleration(points(values), now=NOW)
            strength = compute_strength(metrics)
            assert 0.0 <= strength <= 100.0


class TestLifecycle:
    def test_status_transitions_are_valid(self):
        for previous in SignalStatus:
            for values in ([1], [1, 2], [1, 10, 100], [100, 50, 10]):
                metrics = compute_growth_acceleration(points(values), now=NOW)
                status, strength = classify(metrics, previous_status=previous)
                assert status in SignalStatus
                assert 0.0 <= strength <= 100.0

    def test_breakout_requires_high_strength(self):
        metrics = compute_growth_acceleration(
            points([10, 60, 500, 5000]), now=NOW
        )
        status, strength = classify(metrics)
        if strength >= settings.detect_breakout_strength:
            assert status == SignalStatus.BREAKOUT

    def test_fading_is_not_actionable(self):
        assert not is_actionable(SignalStatus.FADING)
        assert is_actionable(SignalStatus.BREAKOUT)
        assert is_actionable(SignalStatus.RISING)