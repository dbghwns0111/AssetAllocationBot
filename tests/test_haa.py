"""strategy/haa.py 순수 함수 테스트 — 합성 가격으로 신호 규칙과 월말 확정 판정을 검증한다."""

from datetime import date, datetime, timedelta

import pytest

from strategy import haa


def _series(start: date, end: date, monthly_growth: float, base: float = 100.0):
    """평일마다 가격을 만들되, 월별로 일정한 비율로 성장하는 시계열."""
    out, d, px, cur_month = [], start, base, (start.year, start.month)
    while d <= end:
        if (d.year, d.month) != cur_month:
            px *= 1 + monthly_growth
            cur_month = (d.year, d.month)
        if d.weekday() < 5:
            out.append((d, px))
        d += timedelta(days=1)
    return out


def _prices(growth: dict, end: date = date(2026, 9, 30)):
    start = date(2024, 1, 1)
    return {t: _series(start, end, growth.get(t, 0.0)) for t in haa.ALL_TICKERS}


NOW_AFTER_CLOSE = datetime(2026, 10, 2, 10, 0)   # 뉴욕 10월 2일 → 9월 확정


def test_canary_negative_goes_full_defensive():
    g = {t: 0.02 for t in haa.ALL_TICKERS}
    g.update(TIP=-0.01, BIL=0.003, IEF=-0.005)
    sig = haa.compute_signal(_prices(g), NOW_AFTER_CLOSE)
    assert sig["mode"] == "defensive"
    assert sig["weights"] == {"BIL": 1.0}
    assert sig["apply_month"] == "2026-10"


def test_offensive_top4_equal_weight():
    g = {"TIP": 0.01, "BIL": 0.002, "SPY": 0.05, "IWM": 0.04, "VEA": 0.03, "VWO": 0.025,
         "VNQ": 0.01, "DBC": 0.005, "IEF": 0.004, "TLT": 0.001}
    sig = haa.compute_signal(_prices(g), NOW_AFTER_CLOSE)
    assert sig["mode"] == "offensive"
    assert sig["weights"] == {"IWM": 0.25, "SPY": 0.25, "VEA": 0.25, "VWO": 0.25}
    assert sig["ranking"][:4] == ["SPY", "IWM", "VEA", "VWO"]


def test_negative_momentum_in_top4_replaced_by_best_defensive():
    # 공격자산 대부분 음수 → 상위 4개 중 일부가 음수, 그 몫은 BIL/IEF 중 나은 쪽
    g = {"TIP": 0.01, "BIL": 0.001, "IEF": 0.003, "SPY": 0.02, "IWM": 0.01,
         "VEA": -0.01, "VWO": -0.02, "VNQ": -0.03, "DBC": -0.04, "TLT": -0.05}
    sig = haa.compute_signal(_prices(g), NOW_AFTER_CLOSE)
    assert sig["mode"] == "mixed"
    assert sig["defensive_asset"] == "IEF"
    # 상위 4개 = SPY, IWM, IEF(공격자산으로서 3위), VEA(음수) → VEA 몫이 IEF 로
    assert sig["weights"] == {"IEF": 0.5, "IWM": 0.25, "SPY": 0.25}
    assert abs(sum(sig["weights"].values()) - 1) < 1e-9


def test_momentum_is_unweighted_average():
    g = {t: 0.01 for t in haa.ALL_TICKERS}
    sig = haa.compute_signal(_prices(g), NOW_AFTER_CLOSE)
    spy = next(a for a in sig["assets"] if a["ticker"] == "SPY")
    expected = sum((1.01 ** k - 1) for k in (1, 3, 6, 12)) / 4
    assert spy["momentum"] == pytest.approx(expected)


@pytest.mark.parametrize("now, complete", [
    (datetime(2026, 9, 30, 15, 59), False),   # 월말 마지막 평일, 장중
    (datetime(2026, 9, 30, 16, 30), True),    # 장 마감 후
    (datetime(2026, 10, 1, 0, 5), True),      # 다음 달
])
def test_month_complete_on_last_weekday(now, complete):
    assert haa.month_complete((2026, 9), date(2026, 9, 30), now) is complete


def test_month_ending_on_holiday_completes_next_month():
    # 마지막 평일 데이터가 없는(휴장) 달: 같은 달에는 미확정, 다음 달이 되면 확정
    assert haa.month_complete((2026, 5), date(2026, 5, 28), datetime(2026, 5, 29, 20, 0)) is False
    assert haa.month_complete((2026, 5), date(2026, 5, 28), datetime(2026, 6, 1, 9, 0)) is True


def test_signal_uses_previous_month_while_current_is_partial():
    p = _prices({t: 0.01 for t in haa.ALL_TICKERS}, end=date(2026, 10, 2))
    sig = haa.compute_signal(p, NOW_AFTER_CLOSE)
    assert sig["asof"] == "2026-09-30" and sig["apply_month"] == "2026-10" and not sig["partial"]
    preview = haa.compute_signal(p, NOW_AFTER_CLOSE, use_partial=True)
    assert preview["asof"] == "2026-10-02" and preview["apply_month"] == "2026-11" and preview["partial"]


def test_history_returns_follow_signal_weights():
    g = {t: 0.01 for t in haa.ALL_TICKERS}
    rows = haa.signal_history(_prices(g), NOW_AFTER_CLOSE, months=6)
    assert len(rows) == 6
    assert rows[0]["apply_month"] == "2026-10" and rows[0]["return"] is None
    assert rows[1]["return"] == pytest.approx(0.01)


def test_cash_proxy_weight_reported():
    # BIL 이 선택되면 그 비중이 cash_weight 로 내려가 화면/계산기가 현금으로 처리한다
    g = {t: 0.02 for t in haa.ALL_TICKERS}
    g.update(TIP=-0.01, BIL=0.003, IEF=-0.005)
    sig = haa.compute_signal(_prices(g), NOW_AFTER_CLOSE)
    assert sig["cash_proxy"] == "BIL" and sig["cash_weight"] == 1.0
    g.update(TIP=0.01)
    sig = haa.compute_signal(_prices(g), NOW_AFTER_CLOSE)
    assert sig["cash_weight"] == 0.0
