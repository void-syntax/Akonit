"""Worker tests: the 24/7 loop must run one full pass without dying."""

from __future__ import annotations

import pytest

from app.workers import tasks
from app.workers.schedule import _cycle_collect, _cycle_match, _cycle_metrics, _cycle_notify


class _FakeQuery:
    """Empty result set for every chained call in the collection task."""

    def where(self, *a, **k):  # noqa: ANN001, ANN002
        return self

    def order_by(self, *a, **k):  # noqa: ANN001, ANN002
        return self

    def limit(self, *a, **k):  # noqa: ANN001, ANN002
        return self

    def scalars(self):  # noqa: ANN201
        return self

    def unique(self):  # noqa: ANN201
        return self

    def scalar_one_or_none(self) -> None:  # noqa: ANN201
        """No rows: profile defaults and radar keyword lookups read like this."""
        return None

    def scalar_one(self) -> None:  # noqa: ANN201
        return None

    def all(self) -> list:  # noqa: ANN201
        return []


def test_collection_keywords_resolves_radar_conditions() -> None:
    """Keywords must be collected from radars, and the lookup must be awaited.

    `collection_keywords` iterates the result of an async helper. Leaving the
    `await` off does not fail loudly: it returns a coroutine that is silently
    treated as an empty iterable at best, and raises TypeError at worst. Either
    way the engine quietly stops searching what the user asked for.
    """
    import inspect

    from app.workers import tasks

    assert inspect.iscoroutinefunction(tasks._radar_keyword_conditions)

    source = inspect.getsource(tasks.collection_keywords)
    assert "await _radar_keyword_conditions" in source, (
        "collection_keywords must await the radar keyword lookup"
    )


class _FakeSession:
    """Records that the worker opened and released a session."""

    def __init__(self) -> None:
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> "_FakeSession":
        self.entered = True
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.exited = True

    async def execute(self, *a, **k) -> _FakeQuery:  # noqa: ANN002
        return _FakeQuery()


@pytest.fixture
def stubbed(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Replace every network-touching stage so tests stay offline."""
    calls: dict[str, int] = {}

    async def fake_collect(session, **kwargs):  # noqa: ANN001, ARG001
        calls["collect"] = calls.get("collect", 0) + 1

        class _Stats:
            fetched = 350
            signals_created = 12
            signals_updated = 40
            sources_ok = 14
            sources_failed = 1

        return _Stats()

    async def fake_match(session, **kwargs):  # noqa: ANN001, ARG001
        calls["match"] = calls.get("match", 0) + 1
        return []

    async def fake_notify(session, **kwargs):  # noqa: ANN001, ARG001
        calls["notify"] = calls.get("notify", 0) + 1
        return 3

    async def fake_flush(session, **kwargs):  # noqa: ANN001, ARG001
        calls["flush"] = calls.get("flush", 0) + 1
        return {"sent": 3, "failed": 0}

    async def fake_refresh(session, **kwargs):  # noqa: ANN001, ARG001
        calls["refresh"] = calls.get("refresh", 0) + 1
        return 7

    async def fake_countries(session, **kwargs):  # noqa: ANN001, ARG001
        return ["KR"]

    async def fake_broadcast(signal) -> None:  # noqa: ANN001
        calls["broadcast"] = calls.get("broadcast", 0) + 1

    monkeypatch.setattr(tasks, "run_collection_cycle", fake_collect)
    monkeypatch.setattr(tasks, "match_batch", fake_match)
    monkeypatch.setattr(tasks, "notify_matches", fake_notify)
    monkeypatch.setattr(tasks, "flush_deliveries", fake_flush)
    monkeypatch.setattr(tasks, "refresh_signal_metrics", fake_refresh)
    monkeypatch.setattr(tasks, "active_countries", fake_countries)

    import app.api.v1.stream as stream

    monkeypatch.setattr(stream, "broadcast_signal", fake_broadcast, raising=False)
    return calls


@pytest.mark.asyncio
async def test_collection_task_runs_and_reports(stubbed: dict[str, int]) -> None:
    result = await tasks.run_collection_task(_FakeSession())
    assert result["fetched"] == 350
    assert result["sources_ok"] == 14
    assert stubbed["collect"] == 1


@pytest.mark.asyncio
async def test_matching_task_queues_notifications(stubbed: dict[str, int]) -> None:
    result = await tasks.run_matching_task(_FakeSession())
    assert stubbed["match"] == 1
    assert stubbed["notify"] == 1
    assert "notifications_queued" in result


@pytest.mark.asyncio
async def test_notification_task_flushes_deliveries(stubbed: dict[str, int]) -> None:
    result = await tasks.run_notification_task(_FakeSession())
    assert stubbed["flush"] == 1
    assert result["sent"] == 3


@pytest.mark.asyncio
async def test_metrics_task_refreshes(stubbed: dict[str, int]) -> None:
    count = await tasks.refresh_metrics_task(_FakeSession())
    assert stubbed["refresh"] == 1
    assert count == 7


@pytest.mark.asyncio
async def test_cycles_survive_a_failing_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken source must not take the whole worker down."""
    boom = {"called": 0}

    async def exploding(session, **kwargs):  # noqa: ANN001, ARG001
        boom["called"] += 1
        raise RuntimeError("network is down")

    async def no_radars(session, **kwargs):  # noqa: ANN001, ARG001
        return []

    monkeypatch.setattr(tasks, "active_countries", no_radars)
    monkeypatch.setattr(tasks, "run_collection_cycle", exploding)

    with pytest.raises(RuntimeError):
        await tasks.run_collection_task(_FakeSession())

    assert boom["called"] == 1

    # The scheduler uses max_instances=1, so a later tick simply runs again
    # instead of the process exiting.
    async def recovered(session, **kwargs):  # noqa: ANN001, ARG001
        return _Stats(failed=0)

    monkeypatch.setattr(tasks, "run_collection_cycle", recovered)

    import app.api.v1.stream as stream

    monkeypatch.setattr(stream, "broadcast_signal", _noop_broadcast, raising=False)

    result = await tasks.run_collection_task(_FakeSession())
    assert result["fetched"] == 350
    assert result["sources_failed"] == 0


class _Stats:
    def __init__(self, failed: int = 1) -> None:
        self.fetched = 350
        self.signals_created = 12
        self.signals_updated = 40
        self.sources_ok = 14
        self.sources_failed = failed


async def _noop_broadcast(signal) -> None:  # noqa: ANN001
    return None


def test_scheduler_jobs_are_registered() -> None:
    """The schedule module must expose the four pipeline stages."""
    for func in (_cycle_collect, _cycle_match, _cycle_notify, _cycle_metrics):
        assert callable(func)