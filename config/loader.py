"""설정 로더 — .env 를 읽어 하나의 dict 로 제공한다 (싱글턴).

이미 설정된 OS 환경변수가 .env 보다 우선한다.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

_cfg: dict | None = None


def _split(value: str | None) -> list[str]:
    return [x.strip() for x in (value or "").split(",") if x.strip()]


def _abs(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def get_config(reload: bool = False) -> dict:
    global _cfg
    if _cfg is not None and not reload:
        return _cfg

    load_dotenv(ROOT / ".env", override=False)
    env = os.getenv

    _cfg = {
        "web": {
            "host": env("HAA_HOST", "127.0.0.1"),
            "port": int(env("HAA_PORT", "5001")),
            "password": env("WEB_PASSWORD", ""),
            "secret_key": env("WEB_SECRET_KEY", ""),
            "ip_whitelist": _split(env("WEB_IP_WHITELIST")),
            "session_days": 30,
        },
        "telegram": {
            "bot_token": env("TELEGRAM_BOT_TOKEN", ""),
            "chat_id": env("TELEGRAM_CHAT_ID", ""),
        },
        "database": {
            "path": str(_abs(env("DB_PATH", "data/haa.db"))),
            "backup_keep": 14,
        },
        "logging": {
            "dir": str(ROOT / "logs"),
            "level": env("LOG_LEVEL", "INFO"),
        },
    }
    return _cfg
