"""입출금(시드 추가·인출) 기록 CRUD.

리밸런싱 기록(records)과 별개로 쌓는다. 입출금일이 어떤 리밸런싱 날짜 이하이면
그 리밸런싱의 총자산에 이미 들어간 돈으로 보고, 마지막 리밸런싱 이후 것은
다음 리밸런싱 때 계산기의 입금 칸으로 불러온다 (판정은 프론트).
"""

from __future__ import annotations

from datetime import datetime

from database.connection import get_conn


def list_flows() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM cashflows ORDER BY flow_date DESC, id DESC").fetchall()
    return [dict(r) for r in rows]


def create_flow(flow_date: str, amount: float, memo: str = "", source: str = "manual") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO cashflows (flow_date, amount, memo, source, created_at) VALUES (?,?,?,?,?)",
            (flow_date, float(amount), memo or "", source,
             datetime.now().isoformat(timespec="seconds")),
        )
        return cur.lastrowid


def delete_flow(fid: int) -> bool:
    with get_conn() as conn:
        return conn.execute("DELETE FROM cashflows WHERE id=?", (fid,)).rowcount > 0
