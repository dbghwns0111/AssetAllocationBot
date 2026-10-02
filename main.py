"""HAA 리밸런싱 도우미 — 진입점.

main.py
  → .env 로드 → 로깅
  → DB 초기화/마이그레이션 + 무결성 검사 + 시작 백업 1회
  → 포트 바인딩 (이미 실행 중이면 여기서 종료 → 중복 실행 시 알림/폴링이 두 벌 뜨지 않음)
  → 텔레그램 Notifier / 스케줄러(월간 신호 알림, DB 백업) / 명령어 수신 스레드
  → waitress 웹서버 (메인 스레드 블록)
"""

from __future__ import annotations

import sys

from config.loader import get_config
from database import connection as db
from database.models import create_tables
from notification.scheduler import HAAScheduler
from notification.telegram import TelegramNotifier
from notification.telegram_handler import TelegramCommandHandler
from utils.logger import get_logger, setup_logging
from web.app import create_app


def main() -> int:
    cfg = get_config()
    setup_logging(cfg["logging"]["dir"], cfg["logging"]["level"])
    log = get_logger("main")

    db.configure(cfg["database"]["path"])
    create_tables()
    if not db.check_integrity():
        log.error("DB 무결성 검사 실패 — data/backups 의 백업으로 복구를 검토하세요.")
    db.backup_database(cfg["database"]["backup_keep"])

    notifier = TelegramNotifier(cfg["telegram"]["bot_token"], cfg["telegram"]["chat_id"])
    sched = HAAScheduler(cfg, notifier)
    app = create_app(cfg, notifier, sched)

    from waitress import create_server
    host, port = cfg["web"]["host"], cfg["web"]["port"]
    try:
        server = create_server(app, host=host, port=port, threads=6)
    except OSError as e:
        log.error("포트 %s:%s 바인딩 실패 (이미 실행 중?): %s", host, port, e)
        return 1

    if host not in ("127.0.0.1", "localhost") and not cfg["web"]["password"]:
        log.warning("외부 접속(%s)이 허용됐는데 WEB_PASSWORD 가 비어 있습니다.", host)

    sched.start()
    TelegramCommandHandler(notifier).start()
    log.info("HAA 리밸런싱 도우미 시작: http://%s:%s (텔레그램 %s)",
             host, port, "사용" if notifier.enabled else "미설정")
    try:
        server.run()
    finally:
        sched.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
