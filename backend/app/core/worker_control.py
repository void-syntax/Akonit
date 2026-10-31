"""Tiny shared control flag for the separately running collection worker."""

from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import UTC, datetime


_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = (
    _BACKEND_ROOT.parent if _BACKEND_ROOT.name.lower() == "backend" else _BACKEND_ROOT
)
_STATE_DIR = _PROJECT_ROOT / "logs"
_PAUSE_FILE = _STATE_DIR / "worker.paused"
_STATUS_FILE = _STATE_DIR / "worker-status.json"
_LOCK_FILE = _STATE_DIR / "worker.lock"
_COLLECT_NOW_FILE = _STATE_DIR / "worker.collect-now"


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


def request_immediate_collection(path: Path = _COLLECT_NOW_FILE) -> None:
    """Queue one full source pass for the background worker."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def consume_immediate_collection(path: Path = _COLLECT_NOW_FILE) -> bool:
    """Consume the queued full-pass request exactly once."""
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def read_worker_status(path: Path = _STATUS_FILE) -> dict:
    """Read the last atomic worker heartbeat shared by UI and API processes."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_worker_status(path: Path = _STATUS_FILE, **updates) -> dict:
    """Write a small heartbeat snapshot without exposing exception contents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = read_worker_status(path)
    data.update(updates)
    data["heartbeat_at"] = datetime.now(UTC).isoformat()
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    os.replace(temp, path)
    return data


def acquire_worker_lock(path: Path = _LOCK_FILE):
    """Hold an OS-level lock so clicking Start twice cannot spawn two workers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle
