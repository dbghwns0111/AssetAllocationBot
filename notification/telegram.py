"""자산배분 전용 텔레그램 봇 클라이언트 (CryptoSplit 봇과 별개의 토큰/채팅).

parse_mode=HTML 로 보낸다. 포맷 오류로 400 이 나면 태그를 벗겨 평문으로
1회 재전송한다 — 포맷 버그 하나로 알림이 통째로 사라지는 것을 막는 안전망.
"""

from __future__ import annotations

import html
import re
import threading

import requests

from utils.logger import get_logger

_log = get_logger("notification.telegram")
_API = "https://api.telegram.org/bot{token}/{method}"


def _strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text))


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = (bot_token or "").strip()
        self.chat_id = str(chat_id or "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def _call(self, method: str, timeout: float = 15, **payload) -> requests.Response:
        return requests.post(_API.format(token=self.bot_token, method=method),
                             json=payload, timeout=timeout)

    def send(self, text: str, html_mode: bool = True, chat_id: str | None = None) -> bool:
        if not self.bot_token:
            return False
        target = chat_id or self.chat_id
        if not target:
            return False
        try:
            payload = {"chat_id": target, "text": text, "disable_web_page_preview": True}
            if html_mode:
                payload["parse_mode"] = "HTML"
            r = self._call("sendMessage", **payload)
            if r.status_code == 400 and html_mode:
                _log.warning("HTML 전송 400 — 평문으로 재전송: %s", r.text[:200])
                r = self._call("sendMessage", chat_id=target, text=_strip_html(text),
                               disable_web_page_preview=True)
            if not r.ok:
                _log.error("텔레그램 전송 실패 %s: %s", r.status_code, r.text[:200])
            return r.ok
        except Exception as e:
            _log.error("텔레그램 전송 오류: %s", e)
            return False

    def send_async(self, text: str) -> None:
        threading.Thread(target=self.send, args=(text,), daemon=True).start()

    def get_updates(self, offset: int | None, timeout: int = 30) -> list:
        payload = {"timeout": timeout, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        r = self._call("getUpdates", timeout=timeout + 10, **payload)
        r.raise_for_status()
        return r.json().get("result", [])

    def set_commands(self, commands: list) -> None:
        try:
            self._call("setMyCommands",
                       commands=[{"command": c, "description": d} for c, d in commands])
        except Exception as e:
            _log.warning("명령어 메뉴 등록 실패: %s", e)
