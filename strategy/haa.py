"""HAA (Hybrid Asset Allocation) — Wouter Keller & Jan Willem Keuning (2023).

- 카나리아: TIP. 13612U 모멘텀 ≤ 0 이면 100% 방어자산.
- 공격자산: SPY, IWM, VEA, VWO, VNQ, DBC, IEF, TLT 중 모멘텀 상위 4개 (각 25%).
  상위 4개 중 모멘텀 ≤ 0 인 자산의 비중은 방어자산으로 대체.
- 방어자산: BIL, IEF 중 모멘텀이 더 높은 하나.
- 13612U = (1개월 + 3개월 + 6개월 + 12개월 수익률) / 4  (가중치 없음)

이 모듈은 네트워크/시계에 의존하지 않는 순수 함수만 둔다 (테스트 용이).
가격 조회와 현재 시각 주입은 strategy/service.py 가 담당한다.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta

CANARY = "TIP"
OFFENSIVE = ["SPY", "IWM", "VEA", "VWO", "VNQ", "DBC", "IEF", "TLT"]
DEFENSIVE = ["BIL", "IEF"]
TOP_N = 4
LOOKBACKS = (1, 3, 6, 12)
ALL_TICKERS = sorted(set(OFFENSIVE + DEFENSIVE + [CANARY]))
TRADABLE = OFFENSIVE + ["BIL"]           # 실제 매매 대상 (TIP 은 신호용)
MASTER = "SPY"                            # 월 달력 기준 종목

NAMES = {
    "SPY": "미국 대형주",
    "IWM": "미국 소형주",
    "VEA": "선진국 주식",
    "VWO": "신흥국 주식",
    "VNQ": "미국 리츠",
    "DBC": "원자재",
    "IEF": "미국 중기채 7-10년",
    "TLT": "미국 장기채 20년+",
    "BIL": "미국 초단기채 (현금성)",
    "TIP": "물가연동채 (카나리아)",
}

MODE_LABEL = {"offensive": "공격", "mixed": "공격+일부 방어", "defensive": "방어"}

# 정규장 종가가 확정됐다고 보는 뉴욕 시각 (16:00 마감 + 여유)
SESSION_CLOSE = time(16, 15)


# ── 월별 데이터 ──────────────────────────────────────────────────────────────

def month_last(series: list) -> dict:
    """[(date, price)] → {(y, m): (마지막 거래일, 종가)}"""
    out: dict = {}
    for d, px in series:
        out[(d.year, d.month)] = (d, px)
    return out


def build_monthly(prices: dict) -> dict:
    """종목별 일별 시계열 → 공통 월 달력의 월말 종가 표.

    반환: {"months": [(y,m)...], "dates": [마지막 거래일...], "close": {t: [price|None ...]}}
    """
    master = month_last(prices[MASTER])
    months = sorted(master)
    per_ticker = {t: month_last(s) for t, s in prices.items()}
    close = {t: [per_ticker[t].get(ym, (None, None))[1] for ym in months] for t in prices}
    return {"months": months, "dates": [master[ym][0] for ym in months], "close": close}


def last_weekday(y: int, m: int) -> date:
    d = date(y, m, calendar.monthrange(y, m)[1])
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def month_complete(ym: tuple, last_date: date, now_ny: datetime) -> bool:
    """해당 월의 월말 종가가 확정됐는지.

    - 뉴욕 날짜가 이미 다음 달 이후면 확정 (휴장일로 끝나는 달도 자연히 처리).
    - 같은 달이면: 마지막 데이터가 그 달 마지막 평일이고 장 마감 이후여야 확정.
    """
    if (now_ny.year, now_ny.month) > ym:
        return True
    return last_date == last_weekday(*ym) and (
        last_date < now_ny.date() or now_ny.time() >= SESSION_CLOSE)


def _ret(close: dict, t: str, i: int, k: int):
    p0, pk = close[t][i], close[t][i - k]
    if p0 is None or pk is None:
        return None
    return p0 / pk - 1


def returns_at(mt: dict, i: int) -> dict:
    """{t: {"r1":..,"r3":..,"r6":..,"r12":..,"momentum":..}}"""
    out = {}
    for t in mt["close"]:
        rs = {f"r{k}": _ret(mt["close"], t, i, k) for k in LOOKBACKS}
        vals = list(rs.values())
        rs["momentum"] = None if None in vals else sum(vals) / len(vals)
        out[t] = rs
    return out


# ── 배분 ─────────────────────────────────────────────────────────────────────

def allocate(mom: dict) -> dict:
    """모멘텀 {t: float} → 목표 비중 및 판단 근거."""
    missing = [t for t in ALL_TICKERS if mom.get(t) is None]
    if missing:
        raise ValueError(f"모멘텀 계산 불가 (데이터 부족): {', '.join(missing)}")

    defensive = max(DEFENSIVE, key=lambda t: mom[t])
    canary_on = mom[CANARY] > 0
    ranking = sorted(OFFENSIVE, key=lambda t: mom[t], reverse=True)
    weights: dict = {}

    if not canary_on:
        top: list = []
        weights[defensive] = 1.0
        mode = "defensive"
    else:
        top = ranking[:TOP_N]
        for t in top:
            target = t if mom[t] > 0 else defensive
            weights[target] = weights.get(target, 0.0) + 1.0 / TOP_N
        mode = "offensive" if all(mom[t] > 0 for t in top) else "mixed"

    return {
        "mode": mode,
        "mode_label": MODE_LABEL[mode],
        "canary": CANARY,
        "canary_momentum": mom[CANARY],
        "canary_on": canary_on,
        "defensive_asset": defensive,
        "top": top,
        "ranking": ranking,
        "weights": {k: round(v, 4) for k, v in sorted(weights.items(), key=lambda x: (-x[1], x[0]))},
    }


def _apply_month(d: date) -> str:
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return f"{y:04d}-{m:02d}"


def _signal_index(mt: dict, now_ny: datetime, use_partial: bool) -> int:
    i = len(mt["months"]) - 1
    if not use_partial and not month_complete(mt["months"][i], mt["dates"][i], now_ny):
        i -= 1
    if i < max(LOOKBACKS):
        raise ValueError("가격 이력이 12개월보다 짧습니다.")
    return i


def compute_signal(prices: dict, now_ny: datetime, use_partial: bool = False) -> dict:
    mt = build_monthly(prices)
    i = _signal_index(mt, now_ny, use_partial)
    last = len(mt["months"]) - 1

    rets = returns_at(mt, i)
    alloc = allocate({t: r["momentum"] for t, r in rets.items()})
    prev = allocate({t: r["momentum"] for t, r in returns_at(mt, i - 1).items()})

    asof = mt["dates"][i]
    partial = not month_complete(mt["months"][i], asof, now_ny)

    # 오늘이 월말 마지막 평일이고 아직 마감 전이면 → 곧 다음 신호가 확정됨을 안내
    next_hint = None
    if not use_partial and i < last:
        ym = mt["months"][last]
        if now_ny.date() == last_weekday(*ym) and now_ny.time() < SESSION_CLOSE:
            next_hint = f"오늘 미국 장 마감 후(한국시간 새벽) {_apply_month(mt['dates'][last])} 신호가 확정됩니다."

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
            "role": "·".join(role),
            "rank": alloc["ranking"].index(t) + 1 if t in OFFENSIVE else None,
            **rets[t],
        })

    latest = {t: s[-1][1] for t, s in prices.items()}
    prev_w, cur_w = set(prev["weights"]), set(alloc["weights"])
    return {
        "asof": asof.isoformat(),
        "apply_month": _apply_month(asof),
        "partial": partial,
        "next_hint": next_hint,
        "price_date": prices[MASTER][-1][0].isoformat(),
        "prices": latest,
        "names": NAMES,
        "tradable": TRADABLE,
        "assets": assets,
        "prev": {"apply_month": _apply_month(mt["dates"][i - 1]), "mode": prev["mode"],
                 "weights": prev["weights"]},
        "added": sorted(cur_w - prev_w),
        "removed": sorted(prev_w - cur_w),
        **alloc,
    }


def signal_history(prices: dict, now_ny: datetime, months: int = 24) -> list:
    """과거 월별 신호 + 그 신호를 따랐을 때 다음 달 수익률 (최신순)."""
    mt = build_monthly(prices)
    last_idx = len(mt["months"]) - 1
    end = _signal_index(mt, now_ny, use_partial=False)
    start = max(max(LOOKBACKS), end - months + 1)

    rows = []
    for i in range(start, end + 1):
        alloc = allocate({t: r["momentum"] for t, r in returns_at(mt, i).items()})
        ret = None
        if i + 1 <= last_idx:
            ret = sum(w * (mt["close"][t][i + 1] / mt["close"][t][i] - 1)
                      for t, w in alloc["weights"].items())
        rows.append({
            "asof": mt["dates"][i].isoformat(),
            "apply_month": _apply_month(mt["dates"][i]),
            "mode": alloc["mode"],
            "mode_label": alloc["mode_label"],
            "canary_momentum": alloc["canary_momentum"],
            "weights": alloc["weights"],
            "return": ret,
            "return_partial": i + 1 == last_idx and not month_complete(
                mt["months"][last_idx], mt["dates"][last_idx], now_ny),
        })
    rows.reverse()
    return rows
