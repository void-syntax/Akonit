from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy.pool import StaticPool

from app.core.database import _build_engine


def _database_path() -> Path:
    return Path(__file__).resolve().parent / f".pool-test-{uuid4().hex}.db"


def _cleanup_database(path: Path) -> None:
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        candidate.unlink(missing_ok=True)


def test_file_sqlite_uses_a_bounded_multi_connection_pool():
    path = _database_path()
    engine = _build_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    try:
        assert not isinstance(engine.pool, StaticPool)
        assert engine.pool.size() == 3
        assert engine.pool._max_overflow == 2
    finally:
        engine.sync_engine.dispose()
        _cleanup_database(path)


def test_in_memory_sqlite_keeps_static_pool_for_shared_test_schema():
    engine = _build_engine("sqlite+aiosqlite:///:memory:")
    try:
        assert isinstance(engine.pool, StaticPool)
    finally:
        engine.sync_engine.dispose()
