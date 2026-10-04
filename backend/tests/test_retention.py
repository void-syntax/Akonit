"""Retention rules: freshness by default, saved signals forever."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.services.retention import expiry_for, run_cleanup


class FakeResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class FakeSession:
    """Records executed statements; returns a configurable rowcount."""

    def __init__(self, rowcount: int = 0) -> None:
        self.rowcount = rowcount
        self.statements: list[str] = []
        self.commits = 0

    async def execute(self, statement, params=None):  # noqa: ANN001
        self.statements.append(str(statement))
        self.params = params
        return FakeResult(self.rowcount)

    async def commit(self) -> None:
        self.commits += 1


def test_expiry_is_ttl_after_first_seen() -> None:
    seen = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert expiry_for(seen) == seen + timedelta(hours=settings.signal_ttl_hours)


def test_expiry_defaults_to_now_when_unknown() -> None:
    before = datetime.now(UTC) + timedelta(hours=settings.signal_ttl_hours)
    result = expiry_for(None)
    after = datetime.now(UTC) + timedelta(hours=settings.signal_ttl_hours)
    assert before <= result <= after


def test_expiry_accepts_naive_datetimes() -> None:
    naive = datetime(2026, 1, 1, 12, 0)
    assert expiry_for(naive).tzinfo is not None


@pytest.mark.asyncio
async def test_cleanup_deletes_expired_unsaved_signals() -> None:
    session = FakeSession(rowcount=5)

    result = await run_cleanup(session)

    assert result["signals"] == 5
    # The query must exclude anything the user saved.
    saved_guard = session.statements[0]
    assert "saved_signals" in saved_guard
    assert "expires_at" in saved_guard
    assert session.commits >= 1


@pytest.mark.asyncio
async def test_cleanup_is_batched_not_one_bulk_delete() -> None:
    session = FakeSession(rowcount=0)

    await run_cleanup(session)

    for statement in session.statements:
        # A bare DELETE over the whole table would lock it; every statement
        # must be bounded by a LIMIT.
        assert "LIMIT :limit" in statement


@pytest.mark.asyncio
async def test_cleanup_does_not_commit_when_nothing_deleted() -> None:
    session = FakeSession(rowcount=0)

    result = await run_cleanup(session)

    assert sum(result.values()) == 0
    assert session.commits == 0


@pytest.mark.asyncio
async def test_cleanup_covers_all_four_stages() -> None:
    session = FakeSession(rowcount=1)

    result = await run_cleanup(session)

    assert set(result) == {"signals", "source_events", "deliveries", "duplicates"}
    assert "source_events" in session.statements[1]
    assert "notification_deliveries" in session.statements[2]
    assert "ROW_NUMBER" in session.statements[3]