"""The worker pause state must be visible across independent processes."""

from pathlib import Path
from uuid import uuid4

from app.core.worker_control import (
    acquire_worker_lock,
    consume_immediate_collection,
    is_worker_paused,
    request_immediate_collection,
    read_worker_status,
    set_worker_paused,
    write_worker_status,
)


def test_worker_pause_state_is_shared_and_reversible() -> None:
    pause_file = Path(__file__).with_name(f".worker-control-{uuid4().hex}.paused")

    try:
        assert not is_worker_paused(pause_file)
        set_worker_paused(True, pause_file)
        assert is_worker_paused(pause_file)
        set_worker_paused(False, pause_file)
        assert not is_worker_paused(pause_file)
    finally:
        pause_file.unlink(missing_ok=True)


def test_worker_heartbeat_is_shared_and_atomic(tmp_path: Path) -> None:
    path = tmp_path / "worker-status.json"
    write_worker_status(path, status="running", collection_state="idle")

    status = read_worker_status(path)
    assert status["status"] == "running"
    assert status["collection_state"] == "idle"
    assert status["heartbeat_at"]


def test_worker_lock_prevents_a_second_instance(tmp_path: Path) -> None:
    path = tmp_path / "worker.lock"
    first = acquire_worker_lock(path)
    assert first is not None
    try:
        assert acquire_worker_lock(path) is None
    finally:
        first.close()

    second = acquire_worker_lock(path)
    assert second is not None
    second.close()


def test_immediate_collection_request_is_consumed_once() -> None:
    request = Path(__file__).with_name(f".collect-now-{uuid4().hex}")
    try:
        request_immediate_collection(request)

        assert consume_immediate_collection(request)
        assert not request.exists()
        assert not consume_immediate_collection(request)
    finally:
        request.unlink(missing_ok=True)
