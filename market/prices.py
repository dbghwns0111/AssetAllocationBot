"""Yahoo Finance 차트 API 로 일별 수정종가(배당·분할 반영)를 받는다.

yfinance/pandas 를 쓰지 않는 이유: 운영 서버(Windows Server 2012 R2)에서
yfinance 의 curl_cffi, pandas 의 numpy 네이티브 휠 설치가 보장되지 않는다.
requests 만으로 v8 chart 엔드포인트를 직접 호출한다.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

import requests

from utils.logger import get_logger

_log = get_logger("market.prices")

_URLS = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{t}",
    "https://query2.finance.yahoo.com/v8/finance/chart/{t}",
)
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
CACHE_SECONDS = 30 * 60

Series = list  # list[tuple[date, float]] — 날짜 오름차순

# 조회 조건(티커 묶음 + 기간)별 캐시 — 신호용(5y)과 백테스트용(max)이 서로 밀어내지 않게
_cache: dict = {}            # key -> {"ts", "data", "fetched_at"}
_locks: dict = {}            # key -> Lock (같은 조건의 동시 조회만 직렬화)
_locks_guard = threading.Lock()


def _fetch_one(session: requests.Session, ticker: str, range_: str) -> Series:
    last_err: Exception | None = None
    for attempt in range(3):
        url = _URLS[attempt % len(_URLS)].format(t=ticker)
        try:
            params = {"interval": "1d", "events": "div,splits", "includeAdjustedClose": "true"}
            if range_ == "max":
                # range=max 를 주면 Yahoo 가 월봉으로 바꿔 내려준다 → 기간을 직접 지정해 일봉 유지
                params.update(period1=946684800, period2=int(time.time()))   # 2000-01-01 ~ 현재
            else:
                params["range"] = range_
            r = session.get(url, params=params, timeout=30)
            r.raise_for_status()
            res = r.json()["chart"]["result"][0]
            offset = int(res["meta"].get("gmtoffset") or 0)
            stamps = res.get("timestamp") or []
            adj = res["indicators"]["adjclose"][0]["adjclose"]
            by_date: dict[date, float] = {}
            for ts, px in zip(stamps, adj):
                if px is None:
                    continue
                d = datetime.fromtimestamp(ts + offset, tz=timezone.utc).date()
                by_date[d] = float(px)
            if not by_date:
                raise ValueError("빈 데이터")
            return sorted(by_date.items())
        except Exception as e:  # 네트워크/형식 오류 → 재시도
            last_err = e
            time.sleep(1 + attempt)
    raise RuntimeError(f"{ticker} 가격 조회 실패: {last_err}")


def fetch_prices(tickers: list[str], force: bool = False, range_: str = "5y",
                 ttl: float = CACHE_SECONDS) -> dict:
    """{"series": {ticker: Series}, "fetched_at": datetime, "stale": bool}

    조건별 메모리 캐시(기본 30분). 조회 실패 시 이전 캐시가 있으면 stale=True 로 반환.
    """
    key = (tuple(sorted(tickers)), range_)
    with _locks_guard:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:
        entry = _cache.get(key)
        if entry and not force and time.time() - entry["ts"] < ttl:
            return {"series": entry["data"], "fetched_at": entry["fetched_at"], "stale": False}

        try:
            with requests.Session() as s:
                s.headers["User-Agent"] = _UA
                with ThreadPoolExecutor(max_workers=5) as ex:
                    results = list(ex.map(lambda t: _fetch_one(s, t, range_), tickers))
            data = dict(zip(tickers, results))
        except Exception as e:
            if entry:
                _log.warning("가격 조회 실패, 이전 캐시 사용: %s", e)
                return {"series": entry["data"], "fetched_at": entry["fetched_at"], "stale": True}
            raise

        entry = {"ts": time.time(), "data": data, "fetched_at": datetime.now()}
        _cache[key] = entry
        _log.info("가격 조회 완료: %d종목 (%s)", len(data), range_)
        return {"series": data, "fetched_at": entry["fetched_at"], "stale": False}
