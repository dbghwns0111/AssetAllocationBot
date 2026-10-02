"""텔레그램 명령어 수신 (long-polling, 데몬 스레드).

설정된 TELEGRAM_CHAT_ID 에서 온 메시지에만 응답한다. 봇이 텔레그램 서버로
아웃바운드 연결만 하므로 ZeroTier/방화벽과 무관하게 동작한다.
"""

from __future__ import annotations

import threading
import time

from database import record_repo
from notification import message_builder as mb
from strategy import service
from utils.logger import get_logger

_log = get_logger("notification.telegram_handler")

COMMANDS = [
    ("signal", "이번 달 확정 신호"),
    ("preview", "당월 가격 미리보기"),
    ("momentum", "모멘텀 순위"),
    ("last", "최근 리밸런싱 기록"),
    ("help", "명령어 목록"),
]


class TelegramCommandHandler(threading.Thread):
    def __init__(self, notifier):
        super().__init__(name="telegram-handler", daemon=True)
        self.notifier = notifier
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def _handle(self, text: str) -> str:
        cmd = text.strip().split()[0].split("@")[0].lower()
        if cmd in ("/start", "/help"):
            return mb.build_help()
        if cmd == "/signal":
            return mb.build_signal(service.get_signal())
        if cmd == "/preview":
            return mb.build_signal(service.get_signal(use_partial=True), preview=True)
        if cmd == "/momentum":
            return mb.build_momentum(service.get_signal())
        if cmd == "/last":
            return mb.build_last_record(record_repo.latest_record())
        return mb.build_help()

    def run(self):
        if not self.notifier.enabled:
            _log.info("텔레그램 미설정 — 명령어 수신 비활성")
            return
        self.notifier.set_commands(COMMANDS)

        offset = None
        try:  # 꺼져 있던 동안 쌓인 명령은 버린다 (재시작 직후 옛 명령 일괄 실행 방지)
            pending = self.notifier.get_updates(offset=-1, timeout=0)
            if pending:
                offset = pending[-1]["update_id"] + 1
        except Exception as e:
            _log.warning("초기 업데이트 조회 실패: %s", e)

        backoff = 5
        _log.info("텔레그램 명령어 수신 시작")
        while not self._stop_event.is_set():
            try:
                updates = self.notifier.get_updates(offset, timeout=30)
                backoff = 5
            except Exception as e:
                _log.warning("getUpdates 실패 (%ds 후 재시도): %s", backoff, e)
                self._stop_event.wait(backoff)
                backoff = min(backoff * 2, 300)
                continue

            for u in updates:
                offset = u["update_id"] + 1
                msg = u.get("message") or {}
                chat_id = str((msg.get("chat") or {}).get("id", ""))
                text = msg.get("text") or ""
                if chat_id != self.notifier.chat_id:
                    _log.warning("허용되지 않은 채팅의 메시지 무시: %s", chat_id)
                    continue
                if not text.startswith("/"):
                    continue
                try:
                    reply = self._handle(text)
                except Exception as e:
                    _log.exception("명령 처리 실패: %s", text)
                    reply = mb.build_error(text.split()[0], e)
                self.notifier.send(reply)
            time.sleep(0.2)
