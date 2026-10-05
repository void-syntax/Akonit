"""Publication-age parsing.

YouTube abbreviates relative times aggressively ('8mo ago', '3d ago', '14h
ago'), and the original pattern required whitespace between the number and the
unit. It therefore matched almost nothing, every video came back undated, and
the freshness filter could not tell a fresh upload from a five-year-old re-upload.
These cases pin the behaviour that bug produced.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.pipeline.collectors.youtube import parse_relative_time


@pytest.mark.parametrize(
    ("text", "expected_delta"),
    [
        ("45s ago", timedelta(seconds=45)),
        ("3d ago", timedelta(days=3)),
        ("1d ago", timedelta(days=1)),
        ("14h ago", timedelta(hours=14)),
        ("2 hrs ago", timedelta(hours=2)),
        ("18 minutes ago", timedelta(minutes=18)),
        ("1 minute ago", timedelta(minutes=1)),
        ("2 weeks ago", timedelta(weeks=2)),
        ("8mo ago", timedelta(days=30 * 8)),
        ("5y ago", timedelta(days=365 * 5)),
        # Prefixed forms YouTube also emits.
        ("Streamed 3 days ago", timedelta(days=3)),
        ("Premiered 2 hours ago", timedelta(hours=2)),
        ("Viewed 5 months ago", timedelta(days=30 * 5)),
    ],
)
def test_parses_every_format(text: str, expected_delta: timedelta) -> None:
    parsed = parse_relative_time(text)
    assert parsed is not None, f"{text!r} should be understood"
    # Allow a minute of slack for the clock ticking during the test.
    assert abs((datetime.now().astimezone() - parsed) - expected_delta) < timedelta(
        minutes=1
    )


@pytest.mark.parametrize("text", [None, "", "garbage", "ago", "views"])
def test_rejects_unparseable(text: str | None) -> None:
    """An unknown age must stay unknown rather than defaulting to 'now'.

    Defaulting to now would make an undated item look brand new, which is the
    opposite of what a freshness-first feed needs.
    """
    assert parse_relative_time(text) is None
