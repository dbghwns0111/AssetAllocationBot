"""전략 서비스 — 가격 조회 + 현재 뉴욕 시각을 주입해 haa 순수 함수를 호출한다."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from market.prices import fetch_prices
from strategy import haa

NY = ZoneInfo("America/New_York")


def now_ny() -> datetime:
    return datetime.now(NY).replace(tzinfo=None)


def _prices(force: bool = False) -> dict:
    return fetch_prices(haa.ALL_TICKERS, force=force)


def get_signal(use_partial: bool = False, force: bool = False) -> dict:
    p = _prices(force)
    sig = haa.compute_signal(p["series"], now_ny(), use_partial=use_partial)
    sig["fetched_at"] = p["fetched_at"].strftime("%Y-%m-%d %H:%M:%S")
    sig["stale"] = p["stale"]
    return sig


def get_history(months: int = 24) -> list:
    return haa.signal_history(_prices()["series"], now_ny(), months=months)
