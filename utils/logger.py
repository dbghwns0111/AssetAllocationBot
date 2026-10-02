"""로깅 — logs/haa.log (회전) + 콘솔."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_configured = False


def setup_logging(log_dir: str, level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    root = logging.getLogger("haa")
    root.setLevel(level.upper())

    fh = RotatingFileHandler(Path(log_dir) / "haa.log", maxBytes=5 * 1024 * 1024,
                             backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # pythonw(작업 스케줄러)로 실행하면 콘솔이 없다
    if sys.stderr is not None:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"haa.{name}")
