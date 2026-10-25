"""Tests for ETag generation module."""

from __future__ import annotations

import pytest
from app.core.etag import generate_etag


def test_generate_etag():
    etag1 = generate_etag(b"hello world")
    etag2 = generate_etag(b"hello world")
    etag3 = generate_etag(b"different content")

    assert etag1 == etag2
    assert etag1 != etag3
    assert etag1.startswith('"')
    assert etag1.endswith('"')
