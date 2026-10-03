"""백테스트 서비스 — 가격 조회 + 조건 정규화 + 결과 조립 + 기본 결과 캐시.

기본 조건(DEFAULT) 결과는 서버 시작 시 백그라운드로 미리 계산하고 스케줄러가 매일 갱신한다.
웹에 접속하면 바로 결과가 보이도록 하기 위함 (사용자 요청: 일반 백테스트 프로그램처럼 —
기본 결과 즉시 표시, 옵션 변경 후 [실행] 을 눌러야 재계산).
"""

from __future__ import annotations

import threading
from datetime import datetime

from market.prices import fetch_prices
from strategy import backtest as bt
from strategy import haa
from strategy.benchmarks import BENCHMARKS, DEFAULT_BENCHMARKS, benchmark_tickers, fixed_signal
from strategy.service import now_ny
from utils.logger import get_logger

_log = get_logger("strategy.backtest_service")

FX_TICKER = "KRW=X"
PRICE_TTL = 6 * 3600
DEFAULT = {"strategy": "haa", "start": None, "end": None, "slippage": 0.001,
           "cash": "cash", "currency": "usd", "bench": list(DEFAULT_BENCHMARKS)}

_default_lock = threading.Lock()
_default: dict = {"result": None}


def all_tickers() -> list:
    t = set(benchmark_tickers()) | {FX_TICKER}
    for s in bt.STRATEGIES.values():
        t |= set(s["tickers"])
    return sorted(t)


def normalize(p: dict) -> dict:
    """요청 파라미터 → 검증된 조건. 잘못된 값은 ValueError."""
    out = dict(DEFAULT)
    out.update({k: v for k, v in p.items() if v not in (None, "") and k != "bench"})
    if p.get("bench") is not None:          # 빈 문자열 = 벤치마크 없음 (기본값으로 대체하지 않음)
        out["bench"] = p["bench"]
    if out["strategy"] not in bt.STRATEGIES:
        raise ValueError("알 수 없는 전략입니다.")
    for k in ("start", "end"):
        v = out[k]
        if v is not None:
            v = str(v)
            if len(v) != 7 or v[4] != "-" or not (v[:4].isdigit() and v[5:].isdigit()) or not 1 <= int(v[5:]) <= 12:
                raise ValueError(f"{'시작' if k == 'start' else '종료'} 월 형식이 올바르지 않습니다 (YYYY-MM).")
            out[k] = v
    try:
        out["slippage"] = float(out["slippage"])
    except (TypeError, ValueError):
        raise ValueError("슬리피지 값이 숫자가 아닙니다.")
    if not 0 <= out["slippage"] <= 0.02:
        raise ValueError("슬리피지는 0% ~ 2% 사이로 입력하세요.")
    if out["cash"] not in ("cash", "bil"):
        raise ValueError("BIL 처리 방식이 올바르지 않습니다.")
    if out["currency"] not in ("usd", "krw"):
        raise ValueError("통화가 올바르지 않습니다.")
    bench = out["bench"]
    if isinstance(bench, str):
        bench = [b for b in bench.split(",") if b]
    bad = [b for b in bench if b not in BENCHMARKS]
    if bad:
        raise ValueError(f"알 수 없는 벤치마크: {', '.join(bad)}")
    out["bench"] = [b for b in BENCHMARKS if b in bench]     # 정의 순서로 정렬·중복 제거
    if out["start"] and out["end"] and out["start"] > out["end"]:
        raise ValueError("시작 월이 종료 월보다 늦습니다.")
    return out


def _is_default(p: dict) -> bool:
    return p == normalize({})


def compute(params: dict) -> dict:
    p = normalize(params)
    prices = fetch_prices(all_tickers(), range_="max", ttl=PRICE_TTL)
    mt = haa.build_monthly(prices["series"])
    labels = [bt.month_label(ym) for ym in mt["months"]]

    strat = bt.STRATEGIES[p["strategy"]]
    sig_fns = [strat["signal"]] + [fixed_signal(BENCHMARKS[b]["weights"]) for b in p["bench"]]
    extra = ("BIL",) + ((FX_TICKER,) if p["currency"] == "krw" else ())
    auto_start = bt.first_valid_index(mt, sig_fns, extra)

    # 마지막 확정 월 (진행 중인 달 제외)
    last = len(mt["months"]) - 1
    if not haa.month_complete(mt["months"][last], mt["dates"][last], now_ny()):
        last -= 1

    # 사용자 기간: start/end 는 "수익률이 발생하는 월" 기준 → 신호 시점은 그 전월 말
    start_i = auto_start
    if p["start"] and p["start"] in labels:
        start_i = max(auto_start, labels.index(p["start"]) - 1)
    elif p["start"] and p["start"] > labels[last]:
        raise ValueError("시작 월이 데이터 범위를 벗어났습니다.")
    end_i = last
    if p["end"] and p["end"] in labels:
        end_i = min(last, labels.index(p["end"]))
    if end_i - start_i < 12:
        raise ValueError("백테스트 기간은 최소 12개월 이상이어야 합니다.")

    fx = FX_TICKER if p["currency"] == "krw" else None
    rf = [mt["close"]["BIL"][j] / mt["close"]["BIL"][j - 1] - 1 for j in range(start_i + 1, end_i + 1)]
    start_label = labels[start_i]

    def series(key, name, kind, fn, cash_proxy):
        recs = bt.run(mt, fn, start_i, end_i, p["slippage"], p["cash"], cash_proxy, fx)
        return {
            "key": key, "name": name, "kind": kind,
            "metrics": bt.metrics(recs, rf, start_label),
            "equity": [1.0] + [r["equity"] for r in recs],
            "drawdown": [0.0] + [r["drawdown"] for r in recs],
        }, recs

    main, recs = series(p["strategy"], strat["name"], "strategy", strat["signal"], strat["cash_proxy"])
    main["heatmap"] = bt.heatmap(recs)
    main["records"] = [{k: r[k] for k in ("month", "signal_asof", "mode", "weights", "traded", "cost", "ret")}
                       for r in reversed(recs)]
    benches = []
    for b in p["bench"]:
        # 벤치마크는 고정 비중 그대로 (BIL 포함 시에도 실제 BIL 로 계산)
        s, _ = series(b, BENCHMARKS[b]["name"], "benchmark", fixed_signal(BENCHMARKS[b]["weights"]), None)
        benches.append(s)

    return {
        "params": {**p, "slippage_pct": round(p["slippage"] * 100, 4)},
        "computed_at": datetime.now().isoformat(timespec="seconds"),
        "price_fetched_at": prices["fetched_at"].isoformat(timespec="seconds"),
        "stale": prices["stale"],
        "meta": {
            "start": labels[start_i + 1], "end": labels[end_i], "months": end_i - start_i,
            "min_month": labels[auto_start + 1], "max_month": labels[last],
            "strategies": [{"key": k, "name": v["name"], "desc": v["desc"]} for k, v in bt.STRATEGIES.items()],
            "benchmarks": [{"key": k, "name": v["name"], "desc": v["desc"]} for k, v in BENCHMARKS.items()],
        },
        "labels": labels[start_i:end_i + 1],
        "strategy": main,
        "benchmarks": benches,
    }


def get(params: dict) -> dict:
    """기본 조건이면 미리 계산된 결과를, 아니면 새로 계산한 결과를 반환."""
    p = normalize(params)
    if _is_default(p):
        with _default_lock:
            if _default["result"] is None:
                _default["result"] = compute({})
            return _default["result"]
    return compute(p)


def refresh_default() -> None:
    """기본 결과 재계산 (서버 시작 시 백그라운드 + 스케줄러 매일)."""
    try:
        res = compute({})
        with _default_lock:
            _default["result"] = res
        m = res["strategy"]["metrics"]
        _log.info("기본 백테스트 갱신: %s~%s CAGR %.2f%% MDD %.2f%%",
                  res["meta"]["start"], res["meta"]["end"], m["cagr"] * 100, m["mdd"] * 100)
    except Exception as e:
        _log.exception("기본 백테스트 계산 실패: %s", e)


def refresh_default_async() -> None:
    threading.Thread(target=refresh_default, name="backtest-default", daemon=True).start()
