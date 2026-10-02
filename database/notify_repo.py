"""알림 발송 이력 — 같은 달 신호를 두 번 보내지 않기 위한 기록 (재시작에도 유지)."""

from __future__ import annotations

from datetime import datetime

from database.connection import get_conn


def was_sent(kind: str, key: str) -> bool:
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM notify_log WHERE kind=? AND key=?", (kind, key)).fetchone() is not None


def mark_sent(kind: str, key: str, detail: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO notify_log (kind, key, detail, sent_at) VALUES (?,?,?,?)",
            (kind, key, detail, datetime.now().isoformat(timespec="seconds")),
        )


def last_sent(kind: str) -> dict | None:
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM notify_log WHERE kind=? ORDER BY sent_at DESC LIMIT 1", (kind,)).fetchone()
    return dict(r) if r else None
