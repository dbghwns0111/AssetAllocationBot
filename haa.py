"""HAA (Hybrid Asset Allocation) - Wouter Keller & Jan Willem Keuning (2023).

- 카나리아: TIP. 13612U 모멘텀 < 0 이면 100% 방어자산.
- 공격자산: SPY, IWM, VEA, VWO, VNQ, DBC, IEF, TLT 중 모멘텀 상위 4개 (각 25%).
  상위 4개 중 모멘텀이 0 이하인 자산의 비중은 방어자산으로 대체.
- 방어자산: BIL, IEF 중 모멘텀이 더 높은 하나.
- 13612U 모멘텀 = (1개월 + 3개월 + 6개월 + 12개월 수익률) / 4  (가중치 없음)
"""
from __future__ import annotations

import time
from datetime import date

import pandas as pd
import yfinance as yf

CANARY = "TIP"
OFFENSIVE = ["SPY", "IWM", "VEA", "VWO", "VNQ", "DBC", "IEF", "TLT"]
DEFENSIVE = ["BIL", "IEF"]
TOP_N = 4
LOOKBACKS = (1, 3, 6, 12)
ALL_TICKERS = sorted(set(OFFENSIVE + DEFENSIVE + [CANARY]))

NAMES = {
    "SPY": "미국 대형주 (S&P 500)",
    "IWM": "미국 소형주 (Russell 2000)",
    "VEA": "선진국 주식",
    "VWO": "신흥국 주식",
    "VNQ": "미국 리츠",
    "DBC": "원자재",
    "IEF": "미국 중기채 (7-10년)",
    "TLT": "미국 장기채 (20년+)",
    "BIL": "미국 단기채 (1-3개월, 현금성)",
    "TIP": "물가연동채 (카나리아)",
}

_CACHE: dict = {"ts": 0.0, "daily": None}
CACHE_SECONDS = 60 * 30


def fetch_daily(force: bool = False) -> pd.DataFrame:
    """수정주가(배당 반영) 일별 종가."""
    if not force and _CACHE["daily"] is not None and time.time() - _CACHE["ts"] < CACHE_SECONDS:
        return _CACHE["daily"]
    raw = yf.download(ALL_TICKERS, period="5y", interval="1d", auto_adjust=True, progress=False)
    daily = raw["Close"].dropna(how="all")
    missing = [t for t in ALL_TICKERS if t not in daily.columns or daily[t].dropna().empty]
    if missing:
        raise RuntimeError(f"가격 데이터를 받지 못했습니다: {', '.join(missing)}")
    daily = daily.ffill()
    _CACHE.update(ts=time.time(), daily=daily)
    return daily


def to_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    monthly = daily.resample("ME").last()
    # 월말 라벨 대신 실제 마지막 거래일을 인덱스로 사용
    last_days = daily.index.to_series().resample("ME").last()
    monthly.index = pd.DatetimeIndex(last_days.values)
    return monthly.dropna(how="all")


def momentum_at(monthly: pd.DataFrame, i: int) -> pd.Series:
    p0 = monthly.iloc[i]
    rets = [p0 / monthly.iloc[i - k] - 1 for k in LOOKBACKS]
    return sum(rets) / len(rets)


def returns_at(monthly: pd.DataFrame, i: int) -> dict:
    p0 = monthly.iloc[i]
    return {f"r{k}": (p0 / monthly.iloc[i - k] - 1) for k in LOOKBACKS}


def allocate(mom: pd.Series) -> dict:
    """모멘텀 시리즈 → 목표 비중 및 판단 근거."""
    defensive = max(DEFENSIVE, key=lambda t: mom[t])
    canary_on = bool(mom[CANARY] > 0)
    ranking = sorted(OFFENSIVE, key=lambda t: mom[t], reverse=True)
    weights: dict[str, float] = {}

    if not canary_on:
        weights[defensive] = 1.0
        mode = "defensive"
        top = []
    else:
        top = ranking[:TOP_N]
        for t in top:
            target = t if mom[t] > 0 else defensive
            weights[target] = weights.get(target, 0.0) + 1.0 / TOP_N
        mode = "offensive" if all(mom[t] > 0 for t in top) else "mixed"

    return {
        "mode": mode,
        "canary": CANARY,
        "canary_momentum": float(mom[CANARY]),
        "canary_on": canary_on,
        "defensive_asset": defensive,
        "top": top,
        "ranking": ranking,
        "weights": {k: round(v, 4) for k, v in sorted(weights.items(), key=lambda x: -x[1])},
    }


def _is_partial(ts: pd.Timestamp, today: date) -> bool:
    return (ts.year, ts.month) == (today.year, today.month)


def compute_signal(use_partial: bool = False, force: bool = False) -> dict:
    """가장 최근 완료된 월말 기준 신호 (use_partial=True 면 당월 최신 종가 기준)."""
    daily = fetch_daily(force)
    monthly = to_monthly(daily)
    i = len(monthly) - 1
    if not use_partial and _is_partial(monthly.index[i], date.today()):
        i -= 1

    mom = momentum_at(monthly, i)
    rets = returns_at(monthly, i)
    alloc = allocate(mom)
    asof = monthly.index[i]
    apply_month = (asof + pd.offsets.MonthBegin(1)).strftime("%Y-%m")

    assets = []
    for t in ALL_TICKERS:
        role = []
        if t == CANARY:
            role.append("카나리아")
        if t in OFFENSIVE:
            role.append("공격")
        if t in DEFENSIVE:
            role.append("방어")
        assets.append({
            "ticker": t,
            "name": NAMES.get(t, t),
            "role": "/".join(role),
            "momentum": float(mom[t]),
            **{k: float(v[t]) for k, v in rets.items()},
            "rank": alloc["ranking"].index(t) + 1 if t in OFFENSIVE else None,
        })

    latest_prices = {t: float(daily[t].dropna().iloc[-1]) for t in ALL_TICKERS}
    return {
        "asof": asof.strftime("%Y-%m-%d"),
        "apply_month": apply_month,
        "partial": _is_partial(asof, date.today()),
        "price_date": daily.index[-1].strftime("%Y-%m-%d"),
        "prices": latest_prices,
        "names": NAMES,
        "assets": assets,
        **alloc,
    }


def signal_history(months: int = 24) -> list[dict]:
    """과거 월별 신호와 다음 달 실현 수익률 (완료된 월 기준)."""
    daily = fetch_daily()
    monthly = to_monthly(daily)
    last = len(monthly) - 1
    if _is_partial(monthly.index[last], date.today()):
        last -= 1  # 진행 중인 달은 신호 산출 대상에서 제외

    rows = []
    start = max(max(LOOKBACKS), last - months + 1)
    for i in range(start, last + 1):
        alloc = allocate(momentum_at(monthly, i))
        nxt = None
        if i + 1 < len(monthly):
            r = monthly.iloc[i + 1] / monthly.iloc[i] - 1
            nxt = float(sum(w * r[t] for t, w in alloc["weights"].items()))
        asof = monthly.index[i]
        rows.append({
            "asof": asof.strftime("%Y-%m-%d"),
            "apply_month": (asof + pd.offsets.MonthBegin(1)).strftime("%Y-%m"),
            "mode": alloc["mode"],
            "canary_momentum": alloc["canary_momentum"],
            "weights": alloc["weights"],
            "next_return": nxt,
            "next_partial": i + 1 < len(monthly) and _is_partial(monthly.index[i + 1], date.today()),
        })
    rows.reverse()
    return rows
