"""백테스트 엔진 — 전략 독립. 네트워크/시계에 의존하지 않는 순수 함수만 둔다.

규칙
- 월 i 종가로 신호를 계산하고 같은 종가에 체결, 월 i+1 동안 보유 (HAA 원 논문 방식).
- 거래비용: 슬리피지 한 값. 비용 = slippage × Σ|목표 비중 − 드리프트 비중| (현금 제외).
  매수·매도 양쪽에 부과되며, 시작 시점은 전액 현금에서 매수하는 것으로 본다.
- cash_mode="cash": 신호의 BIL 비중을 현금(수익률 0)으로 보유 — 사용자 실제 운용 방식.
- currency="krw": 달러 수익률에 원/달러 환율 변화를 곱한다 (달러 현금도 환율 영향을 받음).
- 월말 종가 기준이라 MDD 는 월중 낙폭을 반영하지 않는다.

새 전략(BAA, LAA …)은 STRATEGIES 에 signal_fn(mt, i) -> {"weights", "mode"} | None 을 등록하면 된다.
"""

from __future__ import annotations

import math
from statistics import mean, stdev

from strategy import haa

CASH = "CASH"


# ── 전략 등록 ────────────────────────────────────────────────────────────────

def _haa_signal(mt: dict, i: int):
    rets = haa.returns_at(mt, i)
    mom = {t: rets[t]["momentum"] for t in haa.ALL_TICKERS if t in rets}
    try:
        a = haa.allocate(mom)
    except ValueError:      # 아직 12개월 이력이 없는 종목이 있음
        return None
    return {"weights": a["weights"], "mode": a["mode"]}


STRATEGIES = {
    "haa": {"name": "HAA", "desc": "Hybrid Asset Allocation (Keller & Keuning)",
            "tickers": haa.ALL_TICKERS, "signal": _haa_signal, "cash_proxy": haa.CASH_PROXY},
}


# ── 엔진 ─────────────────────────────────────────────────────────────────────

def month_label(ym: tuple) -> str:
    return f"{ym[0]:04d}-{ym[1]:02d}"


def first_valid_index(mt: dict, signal_fns: list, extra_tickers: tuple = ()) -> int:
    """모든 signal_fn 이 값을 내고 extra 티커(BIL 등)가 있는 첫 월 인덱스."""
    for i in range(max(haa.LOOKBACKS), len(mt["months"])):
        if any(mt["close"][t][i] is None for t in extra_tickers):
            continue
        if all(fn(mt, i) is not None for fn in signal_fns):
            return i
    raise ValueError("백테스트에 필요한 가격 이력이 부족합니다.")


def _ret(mt: dict, t: str, j: int) -> float:
    if t == CASH:
        return 0.0
    p1, p0 = mt["close"][t][j], mt["close"][t][j - 1]
    if p1 is None or p0 is None:
        raise ValueError(f"{t} {month_label(mt['months'][j])} 가격 없음")
    return p1 / p0 - 1


def run(mt: dict, signal_fn, start_i: int, end_i: int, slippage: float = 0.0,
        cash_mode: str = "cash", cash_proxy: str = "BIL", fx: str | None = None) -> list:
    """월 start_i 종가에 시작해 end_i 종가까지. 반환: 월별 기록 리스트 (월 start_i+1 … end_i).

    fx: 원화 환산 시 환율 티커 (예: "KRW=X"), 없으면 USD.
    """
    if end_i <= start_i:
        raise ValueError("백테스트 기간이 너무 짧습니다.")
    equity, gross_equity, peak = 1.0, 1.0, 1.0
    drift = {CASH: 1.0}
    out = []
    for i in range(start_i, end_i):
        sig = signal_fn(mt, i)
        if sig is None:
            raise ValueError(f"{month_label(mt['months'][i])} 신호를 계산할 수 없습니다.")
        target = {}
        for t, w in sig["weights"].items():
            key = CASH if (cash_mode == "cash" and t == cash_proxy) else t
            target[key] = target.get(key, 0.0) + w

        traded = sum(abs(target.get(t, 0.0) - drift.get(t, 0.0))
                     for t in set(target) | set(drift) if t != CASH)
        cost = slippage * traded

        r_assets = {t: _ret(mt, t, i + 1) for t in target}
        r_usd = sum(w * r_assets[t] for t, w in target.items())
        fx_mult = 1.0
        if fx:
            f1, f0 = mt["close"][fx][i + 1], mt["close"][fx][i]
            if f1 is None or f0 is None:
                raise ValueError("환율 데이터가 없는 구간입니다.")
            fx_mult = f1 / f0
        gross = (1 + r_usd) * fx_mult - 1
        net = (1 - cost) * (1 + gross) - 1

        equity *= 1 + net
        gross_equity *= 1 + gross
        peak = max(peak, equity)
        drift = {t: w * (1 + r_assets[t]) / (1 + r_usd) for t, w in target.items()} if r_usd > -1 else {CASH: 1.0}

        out.append({
            "month": month_label(mt["months"][i + 1]),
            "signal_asof": mt["dates"][i].isoformat(),
            "mode": sig.get("mode"),
            "weights": sig["weights"],
            "traded": traded,
            "cost": cost,
            "gross": gross,
            "ret": net,
            "equity": equity,
            "gross_equity": gross_equity,
            "drawdown": equity / peak - 1,
        })
    return out


# ── 지표 ─────────────────────────────────────────────────────────────────────

def metrics(records: list, rf: list | None = None, start_label: str | None = None) -> dict:
    """records: run() 결과. rf: 같은 길이의 월 무위험수익률(없으면 0)."""
    n = len(records)
    rets = [r["ret"] for r in records]
    rf = rf or [0.0] * n
    years = n / 12
    end_eq = records[-1]["equity"]
    cagr = end_eq ** (1 / years) - 1
    cagr_gross = records[-1]["gross_equity"] ** (1 / years) - 1
    vol = stdev(rets) * math.sqrt(12) if n > 1 else 0.0
    ex = [r - f for r, f in zip(rets, rf)]
    ex_sd = stdev(ex) if n > 1 else 0.0
    sharpe = mean(ex) / ex_sd * math.sqrt(12) if ex_sd > 0 else None
    down = math.sqrt(mean([min(0.0, e) ** 2 for e in ex]))
    sortino = mean(ex) * 12 / (down * math.sqrt(12)) if down > 0 else None

    # MDD 와 고점·저점·회복 월 (시작점 1.0 을 첫 고점으로 둔다)
    peak_v, peak_m = 1.0, start_label
    mdd, mdd_peak, mdd_trough, mdd_peak_v, trough_i = 0.0, None, None, 1.0, None
    for idx, r in enumerate(records):
        if r["equity"] >= peak_v:
            peak_v, peak_m = r["equity"], r["month"]
        dd = r["equity"] / peak_v - 1
        if dd < mdd:
            mdd, mdd_peak, mdd_trough, mdd_peak_v, trough_i = dd, peak_m, r["month"], peak_v, idx
    recovery = None
    if trough_i is not None:
        recovery = next((r["month"] for r in records[trough_i + 1:] if r["equity"] >= mdd_peak_v), None)

    best = max(records, key=lambda r: r["ret"])
    worst = min(records, key=lambda r: r["ret"])
    modes = [r["mode"] for r in records if r["mode"]]
    return {
        "months": n,
        "total_return": end_eq - 1,
        "cagr": cagr,
        "volatility": vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "mdd": mdd,
        "mdd_peak": mdd_peak,
        "mdd_trough": mdd_trough,
        "mdd_recovery": recovery,
        "calmar": cagr / abs(mdd) if mdd < 0 else None,
        "best_month": {"month": best["month"], "ret": best["ret"]},
        "worst_month": {"month": worst["month"], "ret": worst["ret"]},
        "win_rate": sum(1 for r in rets if r > 0) / n,
        "annual_traded": sum(r["traded"] for r in records) / years,
        "cost_drag": cagr_gross - cagr,
        "defensive_ratio": (sum(1 for m in modes if m == "defensive") / len(modes)) if modes else None,
    }


def heatmap(records: list) -> list:
    """[{year, months: [12개 수익률|None], annual, partial}] (오래된 연도부터)."""
    by_year: dict = {}
    for r in records:
        y, m = int(r["month"][:4]), int(r["month"][5:7])
        by_year.setdefault(y, [None] * 12)[m - 1] = r["ret"]
    out = []
    for y in sorted(by_year):
        months = by_year[y]
        acc = 1.0
        for v in months:
            if v is not None:
                acc *= 1 + v
        out.append({"year": y, "months": months, "annual": acc - 1,
                    "partial": any(v is None for v in months)})
    return out
