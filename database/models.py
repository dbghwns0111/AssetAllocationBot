"""DDL + 마이그레이션. 스키마를 바꿀 때는 기존 DB 가 깨지지 않도록
CREATE TABLE IF NOT EXISTS / _add_column() 으로만 확장한다."""

from __future__ import annotations

from database.connection import get_conn

_DDL = [
    """
    CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rebalance_date TEXT NOT NULL,       -- 실제 매매일 YYYY-MM-DD
        apply_month TEXT,                   -- 신호 적용 월 YYYY-MM
        signal_asof TEXT,                   -- 신호 기준 월말 거래일
        mode TEXT,                          -- offensive / mixed / defensive
        canary_momentum REAL,
        weights TEXT,                       -- JSON {ticker: weight}
        holdings TEXT,                      -- JSON [{ticker, shares, price, value, weight}] 체결 후 보유
        cash REAL,
        total_value REAL,
        memo TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS login_attempts (
        ip TEXT PRIMARY KEY,
        fail_count INTEGER NOT NULL DEFAULT 0,
        window_start REAL,
        locked_until REAL,
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notify_log (
        kind TEXT NOT NULL,                 -- 예: monthly_signal
        key TEXT NOT NULL,                  -- 예: 2026-10 (적용 월)
        detail TEXT,
        sent_at TEXT NOT NULL,
        PRIMARY KEY (kind, key)
    )
    """,
]


def _add_column(conn, table: str, column: str, decl: str) -> None:
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def create_tables() -> None:
    with get_conn() as conn:
        for ddl in _DDL:
            conn.execute(ddl)
        # 마이그레이션 예시: _add_column(conn, "records", "fee", "REAL DEFAULT 0")
