"""Logs estruturados e notificações não bloqueantes."""

import json
import logging
import logging.handlers
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        fields = getattr(record, "event_fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def configure(log_file: Path, level: str) -> logging.Logger:
    logger = logging.getLogger("antigravity_updater")
    for existing in logger.handlers:
        existing.close()
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(getattr(logging, level, logging.INFO))
    try:
        log_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if log_file.parent.is_symlink() or log_file.is_symlink():
            raise OSError("Diretório de log inseguro.")
        handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        os.chmod(log_file, 0o600)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())
    return logger


def event(logger: logging.Logger, name: str, level: int = logging.INFO, **fields: Any) -> None:
    logger.log(level, name, extra={"event_fields": fields})


def notify(mode: str, title: str, message: str) -> bool:
    if mode == "off":
        return False
    executable = shutil.which("notify-send")
    graphical_session = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if not executable or (mode == "auto" and not graphical_session):
        return False
    try:
        result = subprocess.run(
            [executable, "--app-name=Antigravity Updater", title, message],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
