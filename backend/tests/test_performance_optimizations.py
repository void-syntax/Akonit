"""Performance-optimization regression tests.

These tests verify that:
1. match_batch() issues bulk queries instead of per-signal N+1 queries.
2. notify_matches() bulk-loads signals and radars, not one session.get() per match.
3. flush_deliveries() bulk-loads signals and user profiles upfront.
4. The worker scheduler uses per-task fine-grained locks, not a single global lock.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_signal(
    id: str = "sig-1",
    strength: float = 0.8,
    status: str = "RISING",
    first_seen_at: datetime | None = None,
):
    from app.models.enums import SignalStatus

    s = MagicMock()
    s.id = id
    s.title = f"Signal {id}"
    s.description = ""
    s.category = "tech"
    s.hashtags = []
    s.country_code = "US"
    s.source_id = "source-1"
    s.source_url = "https://example.com"
    s.growth = 0.5
    s.current_activity = 100
    s.strength = strength
    s.status = SignalStatus.RISING
    s.first_seen_at = first_seen_at or datetime.now(UTC)
    s.matched_at = None
    s.keywords = []
    return s


def _make_radar(
    id: str = "radar-1",
    user_id: str = "user-1",
    threshold: float = 0.0,
    frequency: str = "INSTANT",
    is_active: bool = True,
    condition_groups: list | None = None,
):
    from app.models.enums import NotificationFrequency

    r = MagicMock()
    r.id = id
    r.user_id = user_id
    r.name = f"Radar {id}"
    r.is_active = is_active
    r.signal_threshold = threshold
    r.notification_frequency = NotificationFrequency.INSTANT
    r.notification_channels = ["WEB_PUSH"]
    r.last_notified_at = None
    r.match_count = 0
    r.last_matched_at = None
    r.condition_groups = condition_groups or []
    return r


def _make_delivery(
    id: str = "del-1",
    signal_id: str = "sig-1",
    user_id: str = "user-1",
    radar_id: str = "radar-1",
    channel: str = "WEB_PUSH",
    status: str = "PENDING",
    attempts: int = 0,
):
    from app.models.enums import DeliveryStatus, NotificationChannel

    d = MagicMock()
    d.id = id
    d.signal_id = signal_id
    d.user_id = user_id
    d.radar_id = radar_id
    d.channel = NotificationChannel.WEB_PUSH
    d.status = DeliveryStatus.PENDING
    d.attempts = 0
    d.payload = {"radar": "Radar radar-1"}
    d.scheduled_for = datetime(2000, 1, 1, tzinfo=UTC)
    return d


# ─────────────────────────────────────────────────────────────────────────────
# 1. match_batch – bulk query verification
# ─────────────────────────────────────────────────────────────────────────────

class _CapturingSession:
    """Records every statement passed to execute() so we can count bulk vs N+1."""

    def __init__(self, signals, radars, radar_signals):
        self._signals = signals
        self._radars = radars
        self._radar_signals = radar_signals
        self.execute_calls = []
        self.added = []
        self.flushed = False
        self.committed = False

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushed = True

    async def commit(self) -> None:
        self.committed = True

    async def execute(self, stmt) -> "_FakeResult":
        self.execute_calls.append(stmt)
        stmt_str = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        # Return the right collection based on which table the query hits
        if "signals" in stmt_str.lower() and "radar" not in stmt_str.lower():
            return _FakeResult(self._signals)
        if "radar_signals" in stmt_str.lower():
            return _FakeResult(self._radar_signals)
        if "radars" in stmt_str.lower():
            return _FakeResult(self._radars)
        return _FakeResult([])


class _FakeResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._rows)


@pytest.mark.asyncio
async def test_match_batch_does_not_issue_per_signal_radar_queries() -> None:
    """match_batch must load radars ONCE regardless of how many signals there are.

    The old implementation called match_signal_to_radars(signal) for each signal,
    which in turn did SELECT radars … for every signal.  The optimised path loads
    all active radars in a single query before the loop.
    """
    from app.models.enums import SignalStatus
    from app.services.radar_service import match_batch

    signals = [_make_signal(id=f"sig-{i}") for i in range(5)]
    # No radars → no matches, but we still exercise the bulk-load path.
    radars: list = []

    session = _CapturingSession(signals, radars, [])

    await match_batch(session, lookback_minutes=60)

    # Count how many times the radars table was queried.
    radar_queries = [
        stmt
        for stmt in session.execute_calls
        if "radars" in str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()
        and "radar_signals" not in str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()
    ]
    # Must be exactly 1, not 5 (one per signal).
    assert len(radar_queries) == 1, (
        f"Expected 1 bulk radar query, got {len(radar_queries)}.  "
        "Likely an N+1 regression: radars are being queried inside the signal loop."
    )


@pytest.mark.asyncio
async def test_match_batch_loads_existing_pairs_in_bulk() -> None:
    """radar_signals must be fetched in one IN() query, not per (radar, signal)."""
    from app.services.radar_service import match_batch

    signals = [_make_signal(id=f"sig-{i}") for i in range(3)]
    radars: list = []
    session = _CapturingSession(signals, radars, [])

    await match_batch(session, lookback_minutes=60)

    radar_signal_queries = [
        stmt
        for stmt in session.execute_calls
        if "radar_signals" in str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()
    ]
    # One bulk IN() query, not one per signal.
    assert len(radar_signal_queries) <= 1, (
        f"Expected ≤1 radar_signals query, got {len(radar_signal_queries)}."
    )


@pytest.mark.asyncio
async def test_match_batch_returns_empty_for_no_signals() -> None:
    """When there are no recent signals, match_batch returns [] without DB work."""
    from app.services.radar_service import match_batch

    session = _CapturingSession([], [], [])
    result = await match_batch(session, lookback_minutes=60)
    assert result == []
    # No commit needed when there is nothing to process.
    assert not session.committed


# ─────────────────────────────────────────────────────────────────────────────
# 2. match_signal_to_radars – eager-load path
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_match_signal_to_radars_loads_radars_with_conditions_eagerly() -> None:
    """match_signal_to_radars must load radars with their condition groups
    in a single query (selectinload), not one query per radar."""
    from app.services.radar_service import match_signal_to_radars

    signal = _make_signal()
    radar = _make_radar(id="r-1", condition_groups=[])

    class _EagerSession:
        def __init__(self) -> None:
            self.execute_calls: list = []
            self.added: list = []

        async def execute(self, stmt) -> _FakeResult:
            self.execute_calls.append(stmt)
            compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
            if "radar_signals" in compiled.lower():
                return _FakeResult([])
            if "radars" in compiled.lower():
                return _FakeResult([radar])
            return _FakeResult([])

        def add(self, obj) -> None:
            self.added.append(obj)

        async def commit(self) -> None:
            pass

    session = _EagerSession()
    outcomes = await match_signal_to_radars(session, signal)

    # Radar query must happen exactly once (with eager-load options).
    radar_queries = [
        c for c in session.execute_calls
        if "radars" in str(c.compile(compile_kwargs={"literal_binds": True})).lower()
        and "radar_signals" not in str(c.compile(compile_kwargs={"literal_binds": True})).lower()
    ]
    assert len(radar_queries) == 1, (
        f"Expected 1 radar query (with eager options), got {len(radar_queries)}."
    )
    # No matches because radar has no conditions (empty groups → trivially passes
    # but signal has no RadarSignals in DB, so one match is made).
    assert isinstance(outcomes, list)


# ─────────────────────────────────────────────────────────────────────────────
# 3. notify_matches – bulk-load signals and radars
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notify_matches_bulk_loads_signals_and_radars() -> None:
    """notify_matches must NOT call session.get(Signal, ...) or
    session.get(Radar, ...) in a per-match loop.  Instead it must issue at most
    one SELECT … WHERE id IN (…) query per entity type."""
    from app.models.enums import SignalStatus
    from app.notifications.dispatcher import notify_matches

    # Build match rows
    match1 = MagicMock()
    match1.is_dismissed = False
    match1.signal_id = "sig-1"
    match1.radar_id = "radar-1"
    match1.notified_at = None

    signal = _make_signal(id="sig-1")
    radar = _make_radar(id="radar-1")
    radar.notification_channels = []
    radar.notification_frequency = __import__(
        "app.models.enums", fromlist=["NotificationFrequency"]
    ).NotificationFrequency.OFF  # OFF → no delivery row created

    get_call_count = 0

    class _BulkSession:
        def __init__(self) -> None:
            self.execute_calls: list = []
            self.added: list = []

        async def get(self, model, pk):
            nonlocal get_call_count
            get_call_count += 1
            return None  # Should NOT be called in the optimised path

        async def execute(self, stmt) -> _FakeResult:
            self.execute_calls.append(stmt)
            compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
            if "radar_signals" in compiled.lower():
                return _FakeResult([match1])
            if "signals" in compiled.lower():
                return _FakeResult([signal])
            if "radars" in compiled.lower():
                return _FakeResult([radar])
            return _FakeResult([])

        async def flush(self) -> None:
            pass

        def add(self, obj) -> None:
            self.added.append(obj)

    session = _BulkSession()
    await notify_matches(session, now=datetime.now(UTC))

    assert get_call_count == 0, (
        f"session.get() was called {get_call_count} time(s) inside notify_matches. "
        "This is an N+1 regression: signals/radars must be bulk-loaded."
    )


@pytest.mark.asyncio
async def test_notify_matches_returns_zero_for_no_pending_matches() -> None:
    """With no un-notified radar signals, the function returns 0."""
    from app.notifications.dispatcher import notify_matches

    class _EmptySession:
        async def execute(self, *a, **k) -> _FakeResult:
            return _FakeResult([])

        async def flush(self) -> None:
            pass

    result = await notify_matches(_EmptySession())
    assert result == 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. flush_deliveries – bulk-load signals and profiles
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_flush_deliveries_bulk_loads_signals() -> None:
    """flush_deliveries must NOT call session.get(Signal, ...) per delivery.
    All signals must be fetched in a single IN() query."""
    from app.notifications.dispatcher import flush_deliveries

    get_call_count = 0

    delivery = _make_delivery()

    class _BulkSession:
        def __init__(self) -> None:
            self.execute_calls: list = []
            self.added: list = []

        async def get(self, model, pk):
            nonlocal get_call_count
            get_call_count += 1
            return None  # Must never be called

        async def execute(self, stmt) -> _FakeResult:
            self.execute_calls.append(stmt)
            compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
            if "notification_deliveries" in compiled.lower():
                return _FakeResult([delivery])
            if "user_profiles" in compiled.lower():
                return _FakeResult([])
            if "signals" in compiled.lower():
                return _FakeResult([])  # Not found → delivery skipped
            return _FakeResult([])

        async def flush(self) -> None:
            pass

        def add(self, obj) -> None:
            self.added.append(obj)

    from app.notifications import telegram as tg_mod
    from app.notifications.dispatcher import TelegramClient

    class _FakeTelegram:
        configured = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def send(self, *a, **k):
            pass

    with patch.object(tg_mod, "TelegramClient", _FakeTelegram), \
         patch("app.notifications.dispatcher.TelegramClient", _FakeTelegram):
        session = _BulkSession()
        result = await flush_deliveries(session, limit=10)

    assert get_call_count == 0, (
        f"session.get() was called {get_call_count} time(s) inside flush_deliveries. "
        "This is an N+1 regression: signals must be bulk-loaded."
    )
    assert "sent" in result
    assert "failed" in result
    assert "processed" in result


@pytest.mark.asyncio
async def test_flush_deliveries_returns_zero_stats_when_empty() -> None:
    """No pending/failed deliveries → all-zero stats returned."""
    from app.notifications.dispatcher import flush_deliveries

    class _EmptySession:
        async def execute(self, *a, **k) -> _FakeResult:
            return _FakeResult([])

        async def flush(self) -> None:
            pass

    result = await flush_deliveries(_EmptySession(), limit=10)
    assert result == {"sent": 0, "failed": 0, "processed": 0}


# ─────────────────────────────────────────────────────────────────────────────
# 5. schedule.py – per-task locks, not a single global lock
# ─────────────────────────────────────────────────────────────────────────────

def test_schedule_uses_separate_per_task_locks() -> None:
    """The schedule module must define per-task asyncio.Lock objects so that
    the collect, match, notify, metrics and cleanup cycles don't serialise
    against each other."""
    from app.workers import schedule

    # All five task locks must exist and be distinct Lock objects.
    locks = [
        schedule._COLLECT_LOCK,
        schedule._MATCH_LOCK,
        schedule._NOTIFY_LOCK,
        schedule._METRICS_LOCK,
        schedule._CLEANUP_LOCK,
    ]
    for lock in locks:
        assert isinstance(lock, asyncio.Lock), (
            f"{lock!r} is not an asyncio.Lock"
        )
    # They must be five *different* lock instances.
    lock_ids = [id(lock) for lock in locks]
    assert len(set(lock_ids)) == 5, (
        "All per-task locks are the same object – they must be independent."
    )


def test_global_lock_still_exists_for_backward_compat() -> None:
    """The _GLOBAL_LOCK name must remain so external callers don't break."""
    from app.workers import schedule

    assert hasattr(schedule, "_GLOBAL_LOCK"), (
        "_GLOBAL_LOCK was removed but may be referenced by external tooling."
    )
    assert isinstance(schedule._GLOBAL_LOCK, asyncio.Lock)


@pytest.mark.asyncio
async def test_collect_and_notify_cycles_can_run_concurrently() -> None:
    """_cycle_collect and _cycle_notify must not share a lock: they should be
    able to run at the same time without one waiting for the other.

    We verify this by acquiring _COLLECT_LOCK externally (simulating a long
    collection cycle) and asserting that _NOTIFY_LOCK is still acquirable
    without waiting.
    """
    from app.workers import schedule

    # If both cycles shared a single lock, acquiring _COLLECT_LOCK would block
    # the notify cycle from acquiring the same lock.
    async with schedule._COLLECT_LOCK:
        # _COLLECT_LOCK is held.  _NOTIFY_LOCK must be free.
        acquired = schedule._NOTIFY_LOCK.locked()
        assert not acquired, (
            "_NOTIFY_LOCK is locked while holding _COLLECT_LOCK — "
            "the two cycles cannot run concurrently."
        )
        # Verify all five task locks are individually acquirable.
        for name, lock in [
            ("_MATCH_LOCK", schedule._MATCH_LOCK),
            ("_NOTIFY_LOCK", schedule._NOTIFY_LOCK),
            ("_METRICS_LOCK", schedule._METRICS_LOCK),
            ("_CLEANUP_LOCK", schedule._CLEANUP_LOCK),
        ]:
            assert not lock.locked(), (
                f"{name} is already locked — tasks must not share locks."
            )
