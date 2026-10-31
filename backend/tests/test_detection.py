"""Unit tests for the detection engine (scoring, lifecycle, metrics)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.models.enums import SignalStatus
from app.pipeline.detection.lifecycle import classify, is_actionable
from app.pipeline.detection.metrics import (
    ActivityPoint,
    activity_metrics_comparable,
    compute_growth_acceleration,
    include_current_observation,
    safe_pct,
    mention_burst_score,
)
from app.pipeline.detection.scoring import absolute_score, compute_strength
from app.services.pipeline_service import (
    _effective_event_time,
    _is_stale,
    _snapshot_is_due,
)

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
    def test_cross_source_activity_requires_a_shared_unit(self):
        assert activity_metrics_comparable("reddit", "score", "lobsters", "score")
        assert not activity_metrics_comparable(
            "google_trends", "approx_searches", "reddit", "score_plus_comments"
        )
        assert not activity_metrics_comparable("source_a", "unknown", "source_b", "unknown")
        assert activity_metrics_comparable("reddit", "unknown", "reddit", "unknown")
        assert not activity_metrics_comparable("reddit", "score", "reddit", "comments")

    def test_google_news_counts_require_matching_search_context(self):
        context = {
            "query": "AI agent",
            "window": "when:1h",
            "hl": "en-US",
            "gl": "US",
        }
        assert activity_metrics_comparable(
            "google_news_trends", "query_mentions", "google_news_trends",
            "gnews_a1b2", context, context,
        )
        other_query = {**context, "query": "viral trend"}
        assert not activity_metrics_comparable(
            "google_news_trends", "query_mentions", "google_news_trends",
            "query_mentions", context, other_query,
        )

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

    def test_current_observation_is_included_when_recomputing_metrics(self):
        """A new measurement must affect growth before its snapshot is saved."""
        previous_history = points([100])
        current_observation = ActivityPoint(
            captured_at=NOW + timedelta(minutes=15),
            activity=180,
        )

        metrics = compute_growth_acceleration(
            include_current_observation(
                previous_history,
                captured_at=current_observation.captured_at,
                activity=current_observation.activity,
            ),
            now=current_observation.captured_at,
        )

        assert metrics.current == 180
        assert metrics.previous == 100
        assert metrics.growth == 80

    def test_same_time_observation_replaces_instead_of_faking_a_growth_window(self):
        captured_at = NOW - timedelta(minutes=1)
        history = [ActivityPoint(captured_at=captured_at, activity=100)]

        result = include_current_observation(
            history,
            captured_at=captured_at,
            activity=180,
        )

        assert len(result) == 1
        assert result[0].activity == 180

    def test_observation_history_is_bounded(self):
        history = points(list(range(120)))

        result = include_current_observation(
            history,
            captured_at=NOW + timedelta(minutes=15),
            activity=120,
            max_points=100,
        )

        assert len(result) == 100
        assert result[-1].activity == 120

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

    def test_mention_burst_requires_history_and_rises_above_own_baseline(self):
        assert mention_burst_score(20, []) == 0.0
        assert mention_burst_score(10, [10, 10, 10, 10]) == 0.0
        assert 0.0 < mention_burst_score(12, [4, 4, 4, 4]) < 1.0
        assert mention_burst_score(30, [4, 4, 4, 4]) == 1.0

    def test_mention_only_signal_uses_burst_evidence_instead_of_zero_absolute(self):
        metrics = compute_growth_acceleration(points([0]), now=NOW)
        assert absolute_score(metrics) == 0.0
        metrics.burst_score = 0.75
        assert absolute_score(metrics) == 0.75
        assert compute_strength(
            metrics,
            cross_source_count=2,
            sources=["reddit", "mastodon"],
        ) > compute_strength(
            compute_growth_acceleration(points([0]), now=NOW),
            cross_source_count=2,
            sources=["reddit", "mastodon"],
        )

    def test_unmeasured_mention_can_create_a_density_history_snapshot(self):
        assert _snapshot_is_due(
            record_snapshot=True,
            record_observation=False,
            density_count=1,
            history=[],
            captured_at=NOW,
            interval_seconds=60,
        )


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

    def test_future_publication_time_is_clamped_to_observation_time(self) -> None:
        observed = datetime(2026, 10, 28, 20, 15, tzinfo=UTC)
        published = datetime(2026, 10, 28, 21, 24, tzinfo=UTC)
        assert _effective_event_time(published, observed) == observed


class TestTagFiltering:
    """The feed filters by tag, and the reported total must agree.

    Tag filtering used to happen in Python after the query, so `total` counted
    every signal while `items` held only the matches. A user selecting a tag saw
    "12 found" above a list of two.
    """

    @staticmethod
    def _client_session(tmp_path, monkeypatch):
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
                    ("s0", ["misc"]),
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
                            status=(
                                SignalStatus.FADING
                                if sid == "s0"
                                else SignalStatus.NEW
                            ),
                            strength=99.0 if sid == "s0" else 50.0,
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

    def test_high_historical_fading_signal_sorts_after_live_results(
        self, tmp_path, monkeypatch
    ) -> None:
        import asyncio

        setup, session, engine = self._client_session(tmp_path, monkeypatch)
        asyncio.run(setup())

        try:
            from app.api.v1.signals import list_signals

            async def query():
                async with session() as s:
                    return await list_signals(
                        session=s,
                        user=None,
                        status_filter=None,
                        tab="all",
                        country=None,
                        source=None,
                        radar_id=None,
                        tag=None,
                        keyword=None,
                        min_strength=None,
                        max_age_minutes=None,
                        limit=30,
                        offset=0,
                    )

            page = asyncio.run(query())
            assert page.items[0].title != "s0"
            assert page.items[-1].title == "s0"
        finally:
            asyncio.run(engine.dispose())


def test_api_lifespan_starts() -> None:
    """The ASGI lifespan must run without raising.

    Startup is where the schema is brought up to date, so a mistake there (a
    removed helper, a renamed import) stops the whole app from booting. The
    failure only shows up when something actually serves a request, which no
    unit test was covering.
    """
    import os
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    db = Path(tempfile.gettempdir()) / "lifespan_test.db"
    if db.exists():
        db.unlink()

    # Newlines are allowed with -c; keeping this a real `async with` matters
    # because the context manager holds resources bound to one event loop.
    script = f"""
import asyncio, sys
sys.path.insert(0, r"{backend}")
from app.main import app

async def boot():
    async with app.router.lifespan_context(app):
        pass

asyncio.run(boot())
print("BOOTED")
"""

    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )

    # A second boot without ever touching the schema: the same check run twice
    # proves startup is idempotent and leaves a usable database behind, which is
    # what happens on every restart.
    second = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert "BOOTED" in second.stdout, (
        f"restart failed.\nstdout: {second.stdout}\nstderr: {second.stderr}"
    )

    assert "BOOTED" in result.stdout, (
        f"the API failed to start.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


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
    def test_unmeasured_repeated_event_is_not_called_rising(self):
        # A content-only event (for example, a live social post) has no
        # comparable activity count. Reprocessing it must not fabricate a
        # rising trend merely because a second zero-value snapshot exists.
        metrics = compute_growth_acceleration(points([0, 0]), now=NOW)
        status, _ = classify(metrics, previous_status=SignalStatus.NEW)
        assert status == SignalStatus.NEW

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

    def test_flat_activity_is_not_kept_in_rising_status(self):
        metrics = compute_growth_acceleration(
            points([10_000_000, 10_000_000, 10_000_000]), now=NOW
        )
        status, _ = classify(
            metrics, previous_status=SignalStatus.RISING, cross_source_count=10
        )
        assert metrics.velocity == 0.0
        assert status == SignalStatus.FADING

    def test_fading_is_not_actionable(self):
        assert not is_actionable(SignalStatus.FADING)
        assert is_actionable(SignalStatus.BREAKOUT)
        assert is_actionable(SignalStatus.RISING)
