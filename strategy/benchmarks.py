"""비교용 벤치마크 — 고정 비중 전략. 백테스트 엔진에서 매월 리밸런싱 + 같은 슬리피지로 계산한다."""

from __future__ import annotations

from strategy.haa import OFFENSIVE

BENCHMARKS = {
    "spy":        {"name": "S&P 500", "desc": "SPY 100% 보유",
                   "weights": {"SPY": 1.0}},
    "qqq":        {"name": "나스닥 100", "desc": "QQQ 100% 보유",
                   "weights": {"QQQ": 1.0}},
    "6040":       {"name": "60/40", "desc": "SPY 60% · IEF 40%",
                   "weights": {"SPY": 0.6, "IEF": 0.4}},
    "allweather": {"name": "올웨더 (간이)", "desc": "SPY 30 · TLT 40 · IEF 15 · GLD 7.5 · PDBC 7.5",
                   "weights": {"SPY": 0.30, "TLT": 0.40, "IEF": 0.15, "GLD": 0.075, "PDBC": 0.075}},
    "permanent":  {"name": "영구 포트폴리오", "desc": "SPY · TLT · GLD · BIL 각 25%",
                   "weights": {"SPY": 0.25, "TLT": 0.25, "GLD": 0.25, "BIL": 0.25}},
    "ew8":        {"name": "8자산 동일비중", "desc": "HAA 공격자산 8종 각 12.5%",
                   "weights": {t: 0.125 for t in OFFENSIVE}},
}

DEFAULT_BENCHMARKS = ["spy", "6040"]


def benchmark_tickers() -> set:
    return {t for b in BENCHMARKS.values() for t in b["weights"]}


def fixed_signal(weights: dict):
    """고정 비중 → 엔진이 요구하는 signal_fn(mt, i) 형태. 데이터가 없는 달이면 None."""
    def fn(mt: dict, i: int):
        if any(mt["close"].get(t, [None] * (i + 1))[i] is None for t in weights):
            return None
        return {"weights": dict(weights), "mode": None}
    return fn
