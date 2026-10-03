"""strategy/backtest.py 엔진 테스트 — 합성 가격으로 비용·지표·현금/원화 처리를 검증한다."""

from datetime import date

import pytest

from strategy import backtest as bt
from strategy import haa
from strategy.benchmarks import BENCHMARKS, fixed_signal
from tests.test_haa import NOW_AFTER_CLOSE, _prices, _series


def _mt(growth, extra=None, end=date(2026, 9, 30)):
    p = _prices(growth, end=end)
    for t, g in (extra or {}).items():
        p[t] = _series(date(2024, 1, 1), end, g)
    return haa.build_monthly(p)


def test_constant_growth_cagr_and_no_drawdown():
    mt = _mt({"SPY": 0.01})
    recs = bt.run(mt, fixed_signal({"SPY": 1.0}), 12, 24, slippage=0.0)
    m = bt.metrics(recs)
    assert m["cagr"] == pytest.approx(1.01 ** 12 - 1)
    assert m["mdd"] == 0 and m["mdd_trough"] is None
    assert m["win_rate"] == 1.0


def test_slippage_charged_on_traded_weight():
    mt = _mt({"SPY": 0.0, "IEF": 0.0})
    # 첫 달: 현금 → SPY 100% 매수 (Σ|Δw| = 1)
    recs = bt.run(mt, fixed_signal({"SPY": 1.0}), 12, 14, slippage=0.01)
    assert recs[0]["traded"] == pytest.approx(1.0)
    assert recs[0]["ret"] == pytest.approx(-0.01)
    assert recs[1]["traded"] == pytest.approx(0.0)      # 같은 비중 유지 → 비용 없음

    # 매월 SPY ↔ IEF 전환: 매도 1 + 매수 1 = 2
    flip = lambda mt_, i: {"weights": {"SPY": 1.0} if i % 2 else {"IEF": 1.0}, "mode": None}
    recs = bt.run(mt, flip, 12, 15, slippage=0.01)
    assert [round(r["traded"], 6) for r in recs] == [1.0, 2.0, 2.0]
    assert recs[-1]["equity"] == pytest.approx(0.99 * 0.98 * 0.98)


def test_drift_reduces_rebalancing_trade():
    # 50/50 에서 한쪽만 오르면 다음 달 리밸런싱 매매량 = 드리프트만큼
    mt = _mt({"SPY": 0.10, "IEF": 0.0})
    recs = bt.run(mt, fixed_signal({"SPY": 0.5, "IEF": 0.5}), 12, 14, slippage=0.0)
    w_spy = 0.5 * 1.1 / (0.5 * 1.1 + 0.5)
    assert recs[1]["traded"] == pytest.approx(2 * (w_spy - 0.5))


def test_cash_mode_zeroes_bil_return():
    mt = _mt({"BIL": 0.01})
    sig = fixed_signal({"BIL": 1.0})
    bil = bt.run(mt, sig, 12, 24, slippage=0.0, cash_mode="bil")
    cash = bt.run(mt, sig, 12, 24, slippage=0.001, cash_mode="cash")
    assert bil[-1]["equity"] == pytest.approx(1.01 ** 12)
    assert all(r["ret"] == 0 for r in cash)               # 현금은 매수 비용도 없음
    assert all(r["traded"] == 0 for r in cash)


def test_krw_conversion():
    mt = _mt({"SPY": 0.01}, extra={"KRW=X": 0.02})
    recs = bt.run(mt, fixed_signal({"SPY": 1.0}), 12, 13, slippage=0.0, fx="KRW=X")
    assert recs[0]["ret"] == pytest.approx(1.01 * 1.02 - 1)


def test_mdd_and_recovery():
    mt = _mt({"SPY": 0.0})
    closes = mt["close"]["SPY"]
    for j, px in zip(range(12, 17), [100, 110, 88, 99, 121]):   # 고점 110 → 저점 88 (−20%) → 121 회복
        closes[j] = px
    recs = bt.run(mt, fixed_signal({"SPY": 1.0}), 12, 16, slippage=0.0)
    m = bt.metrics(recs, start_label="start")
    assert m["mdd"] == pytest.approx(-0.2)
    assert (m["mdd_peak"], m["mdd_trough"], m["mdd_recovery"]) == (recs[0]["month"], recs[1]["month"], recs[3]["month"])


def test_heatmap_annual_compounds():
    mt = _mt({"SPY": 0.01})
    recs = bt.run(mt, fixed_signal({"SPY": 1.0}), 12, 24, slippage=0.0)
    hm = bt.heatmap(recs)
    full = [h for h in hm if not h["partial"]]
    assert all(h["annual"] == pytest.approx(1.01 ** 12 - 1) for h in full)


def test_benchmarks_sum_to_one():
    for b in BENCHMARKS.values():
        assert sum(b["weights"].values()) == pytest.approx(1.0)


def test_engine_matches_signal_history_without_costs():
    # 슬리피지 0 + BIL 그대로면 엔진 월수익률 = 기존 haa.signal_history 수익률
    g = {"TIP": 0.01, "BIL": 0.002, "SPY": 0.03, "IWM": 0.02, "VEA": -0.01, "VWO": 0.015,
         "VNQ": -0.02, "DBC": 0.005, "IEF": 0.004, "TLT": -0.003}
    p = _prices(g)
    mt = haa.build_monthly(p)
    hist = {h["apply_month"]: h["return"] for h in haa.signal_history(p, NOW_AFTER_CLOSE, months=6) if h["return"] is not None}
    last = len(mt["months"]) - 1
    recs = bt.run(mt, bt.STRATEGIES["haa"]["signal"], last - 6, last, slippage=0.0, cash_mode="bil")
    for r in recs:
        if r["month"] in hist:
            assert r["ret"] == pytest.approx(hist[r["month"]])


def test_normalize_params():
    from strategy import backtest_service as bs
    d = bs.normalize({})
    assert d["bench"] == ["spy", "6040"] and d["slippage"] == 0.001 and d["cash"] == "cash"
    assert bs.normalize({"bench": ""})["bench"] == []                     # 빈 값 = 벤치마크 없음
    assert bs.normalize({"bench": "qqq,spy,qqq"})["bench"] == ["spy", "qqq"]
    for bad in [{"slippage": 0.05}, {"bench": "xxx"}, {"start": "2020-13"}, {"cash": "x"},
                {"start": "2021-01", "end": "2020-01"}, {"strategy": "zzz"}]:
        with pytest.raises(ValueError):
            bs.normalize(bad)
