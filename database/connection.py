"""SQLite 연결 + 백업 + 무결성 검사."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from utils.logger import get_logger

_log = get_logger("database.connection")
_db_path: Path | None = None


def configure(path: str) -> None:
    global _db_path
    _db_path = Path(path)
    _db_path.parent.mkdir(parents=True, exist_ok=True)


def db_path() -> Path:
    if _db_path is None:
        raise RuntimeError("database.configure() 가 호출되지 않았습니다.")
    return _db_path


@contextmanager
def get_conn():
    """요청마다 새 연결 (Flask 멀티스레드 안전). 정상 종료 시 commit."""
    conn = sqlite3.connect(db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def check_integrity() -> bool:
    with get_conn() as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    ok = result == "ok"
    if not ok:
        _log.error("DB 무결성 검사 실패: %s", result)
    return ok


def backup_database(keep: int = 14) -> Path | None:
    """data/backups/haa_YYYYmmdd_HHMMSS.db 로 온라인 백업, 오래된 것부터 정리."""
    src = db_path()
    if not src.exists():
        return None
    backup_dir = src.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    dest = backup_dir / f"haa_{datetime.now():%Y%m%d_%H%M%S}.db"
    with sqlite3.connect(src) as s, sqlite3.connect(dest) as d:
        s.backup(d)
    for old in sorted(backup_dir.glob("haa_*.db"))[:-keep]:
        old.unlink(missing_ok=True)
    _log.info("DB 백업 완료: %s", dest.name)
    return dest
