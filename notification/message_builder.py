"""텔레그램 메시지 포맷 — 모든 메시지는 card() 하나를 통과한다.

<b>{이모지} {제목}</b>   ← 이모지는 제목에 하나만
{부제}                   ← 선택
<pre>{본문}</pre>        ← 숫자는 전부 여기 (고정폭 정렬). 이모지 금지
{꼬리말}                 ← 선택 (자유 문장)

- 모든 동적 값은 card() 안에서 이스케이프한다. 이 모듈 밖에서 HTML 태그를
  만들어 넘기지 말 것 (이스케이프 누락 시 텔레그램 400 → 메시지 유실).
- <pre> 한 줄은 표시 폭 36칸 이하 목표 (한글 2칸, _w() 로 계산).
"""

from __future__ import annotations

import html
import unicodedata

from strategy.haa import CANARY, CASH_PROXY, MODE_LABEL

MODE_ICON = {"offensive": "📈", "mixed": "⚖️", "defensive": "🛡️"}


def _esc(v) -> str:
    return html.escape(str(v), quote=False)


def _w(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def _pad(s: str, width: int, right: bool = False) -> str:
    gap = " " * max(0, width - _w(s))
    return gap + s if right else s + gap


def _pct(x, digits: int = 2, sign: bool = True) -> str:
    if x is None:
        return "-"
    return f"{x * 100:+.{digits}f}%" if sign else f"{x * 100:.{digits}f}%"


def _usd(x) -> str:
    return "-" if x is None else f"${x:,.2f}"


def _num(x) -> str:
    return f"{x:,.4f}".rstrip("0").rstrip(".")


def card(icon: str, title: str, body: list | None = None,
         sub: str | None = None, foot: str | None = None) -> str:
    parts = [f"<b>{_esc(icon)} {_esc(title)}</b>"]
    if sub:
        parts.append(_esc(sub))
    if body:
        parts.append("<pre>" + _esc("\n".join(body)) + "</pre>")
    if foot:
        parts.append(_esc(foot))
    return "\n".join(parts)


def _reason(sig: dict) -> str:
    if not sig["canary_on"]:
        return f"카나리아 {CANARY} 모멘텀 ≤ 0 → 전액 방어자산({sig['defensive_asset']})"
    mom = {a["ticker"]: a["momentum"] for a in sig["assets"]}
    bad = [t for t in sig["top"] if mom[t] <= 0]
    if bad:
        return f"상위 4개 중 {', '.join(bad)} 모멘텀 ≤ 0 → 그 비중은 {sig['defensive_asset']}로 대체"
    return f"공격자산 상위 4개에 25%씩"


def build_signal(sig: dict, preview: bool = False) -> str:
    mom = {a["ticker"]: a["momentum"] for a in sig["assets"]}
    body = ["목표 비중"]
    for t, w in sig["weights"].items():
        line = f"{_pad(t, 5)}{_pad(_pct(w, 0, sign=False), 6, right=True)}   {_pad(_pct(mom[t]), 8, right=True)}"
        body.append(line + ("  → 현금" if t == CASH_PROXY else ""))
    body.append("─" * 24)
    body.append(f"{_pad('카나리아 ' + CANARY, 13)}{_pad(_pct(sig['canary_momentum']), 9, right=True)}")
    body.append(f"{_pad('방어자산', 13)}{_pad(sig['defensive_asset'], 9, right=True)}")
    if sig["added"] or sig["removed"]:
        body.append("─" * 24)
        if sig["added"]:
            body.append(f"{_pad('편입', 6)}{', '.join(sig['added'])}")
        if sig["removed"]:
            body.append(f"{_pad('제외', 6)}{', '.join(sig['removed'])}")
    else:
        body.append(f"지난달({sig['prev']['apply_month']})과 종목 동일")

    title = f"HAA {sig['apply_month']} {'미리보기' if preview else '리밸런싱 신호'}"
    sub = f"{MODE_LABEL[sig['mode']]} 모드 · {sig['asof']} 종가 기준"
    foot = _reason(sig)
    if sig["weights"].get(CASH_PROXY):
        foot += f"\n💵 {CASH_PROXY} 비중은 매수하지 않고 현금(USD)으로 보유합니다."
    if preview:
        foot += "\n※ 진행 중인 달의 가격으로 계산한 참고값입니다."
    return card(MODE_ICON[sig["mode"]], title, body, sub=sub, foot=foot)


def build_momentum(sig: dict) -> str:
    body = [f"{_pad('순위', 5)}{_pad('종목', 6)}{_pad('13612U', 9, right=True)}"]
    by_t = {a["ticker"]: a for a in sig["assets"]}
    for t in sig["ranking"]:
        a = by_t[t]
        mark = " *" if t in sig["weights"] else ""
        body.append(f"{_pad(str(a['rank']), 5)}{_pad(t, 6)}{_pad(_pct(a['momentum']), 9, right=True)}{mark}")
    body.append("─" * 22)
    for t in [CANARY, "BIL"]:
        mark = " *" if t in sig["weights"] else ""
        body.append(f"{_pad('-', 5)}{_pad(t, 6)}{_pad(_pct(by_t[t]['momentum']), 9, right=True)}{mark}")
    return card("📋", f"13612U 모멘텀 ({sig['asof']})", body, foot="* 이번 달 편입 종목")


def build_last_record(rec: dict | None) -> str:
    if not rec:
        return card("🗂️", "리밸런싱 기록 없음", foot="웹 페이지의 리밸런싱 탭에서 매매 후 기록을 저장하세요.")
    body = [f"{_pad(h['ticker'], 5)}{_pad(_num(h['shares']), 10, right=True)} @ {_usd(h['price'])}"
            for h in rec["holdings"]] or ["(보유 종목 없음)"]
    body.append("─" * 24)
    body.append(f"{_pad('현금', 8)}{_pad(_usd(rec['cash']), 16, right=True)}")
    body.append(f"{_pad('총자산', 8)}{_pad(_usd(rec['total_value']), 16, right=True)}")
    sub = f"{rec['rebalance_date']} 매매 · {rec.get('apply_month') or '-'} 적용"
    return card("🗂️", "최근 리밸런싱 기록", body, sub=sub, foot=rec.get("memo") or None)


def build_help() -> str:
    body = [
        "/signal    이번 달 HAA 확정 신호",
        "/preview   당월 가격 미리보기",
        "/momentum  모멘텀 순위",
        "/last      최근 리밸런싱 기록",
        "/help      명령어 목록",
    ]
    return card("🤖", "자산배분 봇 명령어", body,
                foot="매월 말 미국 장 마감 후(한국시간 새벽) 새 신호를 자동으로 보냅니다.")


def build_test() -> str:
    return card("✅", "자산배분 봇 연결 테스트", foot="이 메시지가 보이면 알림 설정이 정상입니다.")


def build_error(context: str, err: Exception) -> str:
    return card("⚠️", f"{context} 실패", foot=str(err)[:500])
