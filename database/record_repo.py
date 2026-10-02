"""리밸런싱 기록 CRUD."""

from __future__ import annotations

import json
from datetime import datetime

from database.connection import get_conn


def _row(r) -> dict:
    d = dict(r)
    d["weights"] = json.loads(d["weights"] or "{}")
    d["holdings"] = json.loads(d["holdings"] or "[]")
    return d


def list_records() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM records ORDER BY rebalance_date DESC, id DESC").fetchall()
    return [_row(r) for r in rows]


def latest_record() -> dict | None:
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM records ORDER BY rebalance_date DESC, id DESC LIMIT 1").fetchone()
    return _row(r) if r else None


def create_record(d: dict) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO records (rebalance_date, apply_month, signal_asof, mode, canary_momentum,
                                    weights, holdings, cash, total_value, memo, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                d["rebalance_date"], d.get("apply_month"), d.get("signal_asof"), d.get("mode"),
                d.get("canary_momentum"),
                json.dumps(d.get("weights") or {}),
                json.dumps(d.get("holdings") or []),
                float(d.get("cash") or 0), float(d.get("total_value") or 0),
                d.get("memo") or "",
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        return cur.lastrowid


def update_memo(rid: int, memo: str) -> bool:
    with get_conn() as conn:
        return conn.execute("UPDATE records SET memo=? WHERE id=?", (memo, rid)).rowcount > 0


def delete_record(rid: int) -> bool:
    with get_conn() as conn:
        return conn.execute("DELETE FROM records WHERE id=?", (rid,)).rowcount > 0
