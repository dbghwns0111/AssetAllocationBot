"""ETF 상장 전 기간을 대체 데이터(인덱스펀드·지수)로 이어 붙인다 — 백테스트를 2001년부터 하기 위함.

방식: 실제 ETF 의 첫 거래일 가격에 맞춰, 그 이전은 대체 데이터의 **일별 수익률**로 거슬러 올라간다.
체인은 우선순위 순서 (앞이 실제 ETF). 여러 단계면 뒤에서부터 차례로 이어 붙인다.

주의
- ^SPGSCI 는 원자재 **현물** 지수라 선물 롤 수익이 빠진다 (2009년 GSCI +50% vs DBC +16%).
  PCRIX 가 시작되는 2002-07 이전 원자재 구간에만 쓰는 근사치다.
- ^IRX 는 13주 T-bill **금리(%)** 라서 가격이 아니다 → 일할 이자로 누적한 현금 지수로 바꿔 쓴다.
- 뮤추얼펀드 수정종가는 분배금이 반영되어 ETF 총수익과 비슷하지만 보수 차이는 남는다.
"""

from __future__ import annotations

from datetime import date

# 실제 ETF → 대체 데이터 (앞에서부터 우선)
CHAINS = {
    "SPY":  ["SPY", "VFINX"],
    "IWM":  ["IWM", "NAESX"],
    "VEA":  ["VEA", "VTMGX"],
    "VWO":  ["VWO", "VEIEX"],
    "VNQ":  ["VNQ", "VGSIX"],
    "IEF":  ["IEF", "VFITX"],
    "TLT":  ["TLT", "VUSTX"],
    "TIP":  ["TIP", "VIPSX"],
    "PDBC": ["PDBC", "DBC", "PCRIX", "^SPGSCI"],
    "BIL":  ["BIL", "^IRX"],
    "GLD":  ["GLD", "GC=F"],
    "QQQ":  ["QQQ"],
}

PROXY_NAMES = {
    "VFINX": "뱅가드 S&P500 펀드", "NAESX": "뱅가드 소형주 펀드", "VTMGX": "뱅가드 선진국 펀드",
    "VEIEX": "뱅가드 신흥국 펀드", "VGSIX": "뱅가드 리츠 펀드", "VFITX": "뱅가드 중기국채 펀드",
    "VUSTX": "뱅가드 장기국채 펀드", "VIPSX": "뱅가드 물가연동채 펀드", "DBC": "DBC (원자재 ETF)",
    "PCRIX": "PIMCO 원자재 펀드", "^SPGSCI": "S&P GSCI 현물지수(근사)", "^IRX": "13주 T-bill 금리",
    "GC=F": "금 선물",
}

RATE_TICKERS = {"^IRX"}      # 가격이 아니라 연율 % 금리


def rate_to_index(series: list) -> list:
    """[(date, 연율%)] → [(date, 누적 지수)]: 직전 금리로 경과 일수만큼 이자 누적 (실제/365)."""
    out, idx, prev_d, prev_r = [], 1.0, None, None
    for d, r in series:
        if prev_d is not None:
            idx *= 1 + prev_r / 100 * (d - prev_d).days / 365
        out.append((d, idx))
        prev_d, prev_r = d, r
    return out


def _splice(primary: list, older: list) -> list:
    """primary 시작일 이전을 older 의 수익률로 채운다 (primary 첫 가격에 맞춰 스케일)."""
    if not older:
        return primary
    p0_date, p0 = primary[0]
    anchor = [(d, v) for d, v in older if d <= p0_date]
    if not anchor:
        return primary
    a_date, a_val = anchor[-1]
    scale = p0 / a_val
    return [(d, v * scale) for d, v in older if d < p0_date] + primary


def chain_tickers(tickers, proxies: bool = True) -> list:
    out = set()
    for t in tickers:
        out.update(CHAINS.get(t, [t]) if proxies else [t])
    return sorted(out)


def build(raw: dict, tickers, proxies: bool = True) -> tuple:
    """raw: {티커: 일별 시계열} → ({티커: 이어붙인 시계열}, {티커: 실제 ETF 첫 거래일})"""
    out, etf_start = {}, {}
    for t in tickers:
        chain = CHAINS.get(t, [t]) if proxies else [t]
        series = []
        for src in reversed(chain):                     # 가장 오래된 대체 데이터부터
            s = raw.get(src) or []
            if src in RATE_TICKERS:
                s = rate_to_index(s)
            if not s:
                continue
            series = _splice(s, series) if series else s
        out[t] = series
        etf_start[t] = (raw.get(t) or [(date.max, None)])[0][0]
    return out, etf_start
