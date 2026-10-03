"""REST API (/api/...). 오류 응답은 {"ok": false, "error": "..."}."""

from __future__ import annotations

import math
from datetime import date

from flask import Blueprint, current_app, jsonify, request

from database import notify_repo, record_repo
from notification import message_builder as mb
from notification.scheduler import KIND_SIGNAL, check_and_notify
from strategy import backtest_service, haa, service
from utils.logger import get_logger

_log = get_logger("web.api")
api_bp = Blueprint("api", __name__, url_prefix="/api")


def _err(msg: str, status: int = 400):
    return jsonify({"ok": False, "error": msg}), status


@api_bp.get("/signal")
def signal():
    try:
        return jsonify(service.get_signal(use_partial=request.args.get("partial") == "1",
                                          force=request.args.get("refresh") == "1"))
    except Exception as e:
        _log.exception("신호 계산 실패")
        return _err(f"신호 계산 실패: {e}", 502)


@api_bp.get("/history")
def history():
    try:
        months = max(1, min(int(request.args.get("months", 24)), 48))
        return jsonify(service.get_history(months))
    except Exception as e:
        _log.exception("신호 이력 계산 실패")
        return _err(f"신호 이력 계산 실패: {e}", 502)


@api_bp.get("/backtest")
def backtest():
    """파라미터 없으면 미리 계산된 기본 결과. slippage 는 퍼센트 단위(0.10 = 0.10%)."""
    a = request.args
    params = {k: a.get(k) for k in ("strategy", "start", "end", "cash", "currency", "bench")}
    if a.get("slippage") not in (None, ""):
        try:
            params["slippage"] = float(a["slippage"]) / 100
        except ValueError:
            return _err("슬리피지 값이 숫자가 아닙니다.")
    try:
        return jsonify(backtest_service.get(params))
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        _log.exception("백테스트 실패")
        return _err(f"백테스트 실패: {e}", 502)


# ── 리밸런싱 기록 ────────────────────────────────────────────────────────────

def _num(v, name: str, minimum: float = 0.0) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{name} 값이 숫자가 아닙니다.")
    if math.isnan(x) or math.isinf(x) or x < minimum:
        raise ValueError(f"{name} 값이 올바르지 않습니다.")
    return x


def _validate_record(d: dict) -> dict:
    try:
        date.fromisoformat(str(d.get("rebalance_date", "")))
    except ValueError:
        raise ValueError("리밸런싱 날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).")

    holdings = []
    for h in d.get("holdings") or []:
        t = str(h.get("ticker", "")).upper()
        if t not in haa.TRADABLE:
            raise ValueError(f"알 수 없는 종목: {t}")
        shares = _num(h.get("shares"), f"{t} 수량")
        price = _num(h.get("price"), f"{t} 체결가")
        if shares > 0:
            holdings.append({"ticker": t, "shares": shares, "price": price,
                             "value": round(shares * price, 2)})
    cash = _num(d.get("cash", 0), "현금", minimum=-1e12)   # 소폭 음수(현금 부족) 허용
    total = round(sum(h["value"] for h in holdings) + cash, 2)
    for h in holdings:
        h["weight"] = h["value"] / total if total > 0 else 0

    return {
        "rebalance_date": d["rebalance_date"],
        "apply_month": d.get("apply_month"),
        "signal_asof": d.get("signal_asof"),
        "mode": d.get("mode"),
        "canary_momentum": d.get("canary_momentum"),
        "weights": d.get("weights") or {},
        "holdings": holdings,
        "cash": round(cash, 2),
        "total_value": total,
        "memo": str(d.get("memo") or "")[:500],
    }


@api_bp.get("/records")
def list_records():
    return jsonify(record_repo.list_records())


@api_bp.post("/records")
def create_record():
    try:
        rec = _validate_record(request.get_json(force=True) or {})
    except ValueError as e:
        return _err(str(e))
    rid = record_repo.create_record(rec)
    _log.info("리밸런싱 기록 저장: id=%s %s", rid, rec["rebalance_date"])
    return jsonify({"ok": True, "id": rid, "message": "리밸런싱 기록을 저장했습니다."}), 201


@api_bp.patch("/records/<int:rid>")
def update_memo(rid: int):
    memo = str((request.get_json(force=True) or {}).get("memo") or "")[:500]
    if not record_repo.update_memo(rid, memo):
        return _err("기록을 찾을 수 없습니다.", 404)
    return jsonify({"ok": True, "message": "메모를 저장했습니다."})


@api_bp.delete("/records/<int:rid>")
def delete_record(rid: int):
    if not record_repo.delete_record(rid):
        return _err("기록을 찾을 수 없습니다.", 404)
    _log.info("리밸런싱 기록 삭제: id=%s", rid)
    return jsonify({"ok": True, "message": "기록을 삭제했습니다."})


# ── 시스템 / 텔레그램 ────────────────────────────────────────────────────────

@api_bp.get("/system")
def system():
    notifier = current_app.config.get("NOTIFIER")
    sched = current_app.config.get("SCHEDULER")
    chat = notifier.chat_id if notifier else ""
    return jsonify({
        "telegram_enabled": bool(notifier and notifier.enabled),
        "telegram_chat": (chat[:3] + "…" + chat[-2:]) if len(chat) > 6 else chat,
        "last_signal_notify": notify_repo.last_sent(KIND_SIGNAL),
        "next_runs": sched.next_runs() if sched else {},
        "auth_active": bool(current_app.config["CFG"]["web"].get("password")),
    })


@api_bp.post("/telegram/test")
def telegram_test():
    notifier = current_app.config.get("NOTIFIER")
    if not (notifier and notifier.enabled):
        return _err("텔레그램이 설정되지 않았습니다 (.env 의 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID).")
    if not notifier.send(mb.build_test()):
        return _err("전송 실패 — 토큰/채팅 ID 를 확인하세요.", 502)
    return jsonify({"ok": True, "message": "테스트 메시지를 보냈습니다."})


@api_bp.post("/telegram/signal")
def telegram_signal():
    notifier = current_app.config.get("NOTIFIER")
    if not (notifier and notifier.enabled):
        return _err("텔레그램이 설정되지 않았습니다.")
    try:
        res = check_and_notify(notifier, force=True)
    except Exception as e:
        return _err(f"신호 발송 실패: {e}", 502)
    if not res.get("sent"):
        return _err(res.get("reason") or "전송 실패", 502)
    return jsonify({"ok": True, "message": f"{res['apply_month']} 신호를 보냈습니다."})
