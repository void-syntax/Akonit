"""Regression tests for bugs that only surfaced once the worker actually ran."""

from __future__ import annotations

import inspect

import pytest

from app.notifications import dispatcher
from app.notifications.dispatcher import EPOCH


def test_epoch_sentinel_is_defined() -> None:
    """`EPOCH` was referenced but never defined, breaking every notify run."""
    assert dispatcher.EPOCH is EPOCH
    assert EPOCH.year == 1970
    assert EPOCH.tzinfo is not None


def test_notify_matches_returns_an_int() -> None:
    """The signature promises an int, so callers can accumulate the count."""
    signature = inspect.signature(dispatcher.notify_matches)
    assert signature.return_annotation in (int, "int")


@pytest.mark.asyncio
async def test_notify_matches_returns_zero_when_nothing_matches() -> None:
    class _EmptyResult:
        def where(self, *a, **k):  # noqa: ANN001, ANN002
            return self

        def scalars(self):  # noqa: ANN201
            return self

        def unique(self):  # noqa: ANN201
            return self

        def all(self) -> list:  # noqa: ANN201
            return []

    class _Session:
        async def execute(self, *a, **k) -> _EmptyResult:  # noqa: ANN002
            return _EmptyResult()

        async def commit(self) -> None:
            return None

    queued = await dispatcher.notify_matches(_Session())
    assert isinstance(queued, int)
    assert queued == 0


def test_frequency_delay_covers_every_mode() -> None:
    from datetime import timedelta

    from app.models.enums import NotificationFrequency

    for mode in NotificationFrequency:
        if mode is NotificationFrequency.OFF:
            continue
        assert mode in dispatcher.FREQUENCY_DELAY, f"{mode} has no delay"
    assert dispatcher.FREQUENCY_DELAY[NotificationFrequency.INSTANT] == timedelta(0)