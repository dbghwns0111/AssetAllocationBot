"""웹 접근 보안 — 세션 비밀번호 로그인 + IP 화이트리스트 + CSRF + 브루트포스 방어.

CryptoSplit web/auth.py 와 같은 설계:
- 비밀번호는 .env 의 WEB_PASSWORD 에서만 로드. 미설정이면 인증 비활성(fail-open)
  — pull 후 로그인 불가로 잠기는 일을 막는다.
- IP 화이트리스트(WEB_IP_WHITELIST)는 비밀번호와 독립된 방어선. 비어 있으면 전체 허용,
  127.0.0.1 은 항상 허용. 단일 IP 또는 CIDR 표기.
- 로그인 후 상태 변경 API(POST/PUT/PATCH/DELETE)는 X-CSRF-Token 헤더 필수.
- IP 당 15분 내 5회 실패 시 10분 잠금 (login_attempts 테이블에 영속화).
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import secrets
import threading
import time
from datetime import timedelta

from flask import (Blueprint, current_app, jsonify, redirect, render_template, request,
                   session, url_for)

from database import auth_repo
from notification import message_builder as mb
from utils.logger import get_logger

_log = get_logger("web.auth")
auth_bp = Blueprint("auth", __name__)

_EXEMPT_ENDPOINTS = {"auth.login", "auth.logout", "static", "dashboard.manifest"}
_LOCAL_IPS = {"127.0.0.1", "::1", "localhost"}
_CSRF_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

_LOGIN_MAX_FAILS = 5
_LOGIN_WINDOW = 900   # 15분
_LOGIN_LOCK = 600     # 10분
_login_lock = threading.Lock()


def _cfg() -> dict:
    return current_app.config["CFG"]["web"]


def _password() -> str:
    return str(_cfg().get("password") or "")


def auth_active() -> bool:
    return bool(_password())


def _ip_allowed(remote: str, whitelist: list) -> bool:
    if remote in _LOCAL_IPS:
        return True
    try:
        addr = ipaddress.ip_address(remote)
    except ValueError:
        return False
    for entry in whitelist:
        try:
            if "/" in entry:
                if addr in ipaddress.ip_network(entry, strict=False):
                    return True
            elif addr == ipaddress.ip_address(entry):
                return True
        except ValueError:
            _log.warning("잘못된 형식의 화이트리스트 항목 무시: %s", entry)
    return False


def _csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_hex(32)
        session["csrf_token"] = token
    return token


def _pw_fingerprint() -> str:
    return hashlib.sha256(_password().encode("utf-8")).hexdigest()[:16]


# ── 브루트포스 방어 ───────────────────────────────────────────────────────────

def _locked_remaining(ip: str) -> int:
    if ip in _LOCAL_IPS:
        return 0
    rec = auth_repo.get_attempt(ip)
    remaining = ((rec or {}).get("locked_until") or 0) - time.time()
    return int(remaining) if remaining > 0 else 0


def _record_fail(ip: str) -> None:
    if ip in _LOCAL_IPS:
        return
    now = time.time()
    with _login_lock:
        rec = auth_repo.get_attempt(ip)
        if rec and now - (rec.get("window_start") or 0) < _LOGIN_WINDOW:
            fail_count = int(rec.get("fail_count") or 0) + 1
            window_start = rec.get("window_start") or now
        else:
            fail_count, window_start = 1, now
        locked_until = (rec.get("locked_until") or 0) if rec else 0
        if fail_count >= _LOGIN_MAX_FAILS:
            locked_until = now + _LOGIN_LOCK
            fail_count = 0
            _log.warning("로그인 잠금 발동: %s", ip)
            notifier = current_app.config.get("NOTIFIER")
            if notifier and notifier.enabled:
                notifier.send_async(mb.card("⚠️", "로그인 잠금 발동",
                                            foot=f"IP {ip} — 연속 {_LOGIN_MAX_FAILS}회 실패로 {_LOGIN_LOCK // 60}분 잠금"))
        auth_repo.upsert_attempt(ip, fail_count, window_start, locked_until)


# ── 설치 ─────────────────────────────────────────────────────────────────────

def init_auth(app) -> None:
    web = app.config["CFG"]["web"]
    secret = web.get("secret_key") or ""
    if not secret:
        secret = os.urandom(32).hex()
        _log.warning("WEB_SECRET_KEY 미설정 — 임의 키 사용 (재시작 시 재로그인 필요)")
    app.secret_key = secret
    app.permanent_session_lifetime = timedelta(days=int(web.get("session_days", 30)))
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_NAME"] = "haa_session"   # 같은 IP 의 CryptoSplit(5000) 쿠키와 분리

    app.register_blueprint(auth_bp)
    app.before_request(_guard)
    app.context_processor(lambda: {"csrf_token": _csrf_token(), "auth_active": auth_active()})

    if not web.get("password"):
        _log.warning("WEB_PASSWORD 미설정 — 로그인 없이 접속 가능한 상태입니다.")


def _deny(status: int, msg: str):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": msg}), status
    return msg, status


def _guard():
    remote = (request.remote_addr or "").strip()

    whitelist = _cfg().get("ip_whitelist") or []
    if whitelist and not _ip_allowed(remote, whitelist):
        _log.warning("화이트리스트 외 IP 접근 차단: %s", remote)
        return _deny(403, "접근이 허용되지 않은 IP 입니다.")

    if not auth_active() or request.endpoint in _EXEMPT_ENDPOINTS:
        return None

    if session.get("authenticated"):
        if session.get("pw_fp") != _pw_fingerprint():   # 비밀번호 변경 → 기존 세션 무효화
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "unauthorized"}), 401
            return redirect(url_for("auth.login"))
        if request.method in _CSRF_METHODS and request.path.startswith("/api/"):
            supplied = request.headers.get("X-CSRF-Token", "")
            if not supplied or not hmac.compare_digest(supplied, str(session.get("csrf_token", ""))):
                _log.warning("CSRF 토큰 불일치: %s %s (%s)", request.method, request.path, remote)
                return jsonify({"ok": False, "error": "csrf_failed"}), 403
        return None

    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return redirect(url_for("auth.login", next=request.path))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if not auth_active():
        return redirect("/")
    remote = (request.remote_addr or "").strip()

    remaining = _locked_remaining(remote)
    if remaining > 0:
        return render_template("login.html",
                               error=f"로그인 시도가 너무 많습니다. 약 {(remaining + 59) // 60}분 후 다시 시도하세요."), 429

    if request.method == "POST":
        if hmac.compare_digest(request.form.get("password", ""), _password()):
            auth_repo.clear_attempt(remote)
            session.clear()
            session.permanent = True
            session["authenticated"] = True
            session["csrf_token"] = secrets.token_hex(32)
            session["pw_fp"] = _pw_fingerprint()
            _log.info("웹 로그인 성공: %s", remote)
            nxt = request.args.get("next") or "/"
            # 오픈 리다이렉트 방지 — "/path" 만 허용 ("//host", "/\\host" 차단)
            if not nxt.startswith("/") or nxt.startswith("//") or nxt.startswith("/\\"):
                nxt = "/"
            return redirect(nxt)
        _record_fail(remote)
        _log.warning("웹 로그인 실패: %s", remote)
        return render_template("login.html", error="비밀번호가 올바르지 않습니다."), 401

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login") if auth_active() else "/")
