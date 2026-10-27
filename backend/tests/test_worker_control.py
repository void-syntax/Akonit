"""The worker pause state must be visible across independent processes."""

from pathlib import Path
from uuid import uuid4

from app.core.worker_control import is_worker_paused, set_worker_paused


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
