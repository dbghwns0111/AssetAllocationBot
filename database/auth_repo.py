"""로그인 브루트포스 방어 상태 영속화 (앱 재시작 후에도 잠금 유지)."""

from __future__ import annotations

from datetime import datetime

from database.connection import get_conn


def get_attempt(ip: str) -> dict | None:
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM login_attempts WHERE ip=?", (ip,)).fetchone()
    return dict(r) if r else None


def upsert_attempt(ip: str, fail_count: int, window_start: float, locked_until: float) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO login_attempts (ip, fail_count, window_start, locked_until, updated_at)
               VALUES (?,?,?,?,?)
               ON CONFLICT(ip) DO UPDATE SET fail_count=excluded.fail_count,
                   window_start=excluded.window_start, locked_until=excluded.locked_until,
                   updated_at=excluded.updated_at""",
            (ip, fail_count, window_start, locked_until, datetime.now().isoformat(timespec="seconds")),
        )


def clear_attempt(ip: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM login_attempts WHERE ip=?", (ip,))
