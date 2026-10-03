"""market/splice.py — ETF 상장 전 구간을 대체 데이터 수익률로 이어 붙이는 로직."""

from datetime import date

import pytest

from market import splice


def test_splice_scales_older_returns_to_etf_start():
    etf = [(date(2010, 1, 4), 50.0), (date(2010, 1, 5), 55.0)]
    proxy = [(date(2009, 12, 31), 8.0), (date(2010, 1, 4), 10.0), (date(2010, 1, 5), 99.0)]
    out, start = splice.build({"SPY": etf, "VFINX": proxy}, ["SPY"])
    assert out["SPY"][0] == (date(2009, 12, 31), pytest.approx(40.0))   # 8/10 × 50
    assert out["SPY"][1:] == etf                                         # ETF 구간은 그대로
    assert start["SPY"] == date(2010, 1, 4)


def test_etf_only_mode_ignores_proxies():
    etf = [(date(2010, 1, 4), 50.0)]
    out, _ = splice.build({"SPY": etf, "VFINX": [(date(2009, 1, 2), 1.0)]}, ["SPY"], proxies=False)
    assert out["SPY"] == etf


def test_rate_to_index_accrues_interest():
    idx = splice.rate_to_index([(date(2020, 1, 1), 3.65), (date(2020, 1, 11), 3.65)])
    assert idx[1][1] == pytest.approx(1 + 0.0365 * 10 / 365)


def test_multi_level_chain():
    a = [(date(2015, 1, 2), 100.0)]
    b = [(date(2010, 1, 4), 20.0), (date(2015, 1, 2), 40.0)]
    c = [(date(2005, 1, 3), 1.0), (date(2010, 1, 4), 2.0)]
    out, _ = splice.build({"PDBC": a, "DBC": b, "PCRIX": c}, ["PDBC"])
    assert out["PDBC"][0] == (date(2005, 1, 3), pytest.approx(25.0))    # 1/2 × 20 × (100/40)
