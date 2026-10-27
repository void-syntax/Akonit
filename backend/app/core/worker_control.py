"""Tiny shared control flag for the separately running collection worker."""

from __future__ import annotations

from pathlib import Path

_PAUSE_FILE = Path(__file__).resolve().parents[3] / "logs" / "worker.paused"


def is_worker_paused(path: Path = _PAUSE_FILE) -> bool:
    """Read the pause state shared between API and worker processes."""
    return path.exists()


def set_worker_paused(paused: bool, path: Path = _PAUSE_FILE) -> None:
    """Persist the pause state so the API can control a separate worker process."""
    if paused:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
    else:
        path.unlink(missing_ok=True)
