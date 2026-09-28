"""Logging persistente y rotativo para diagnóstico de NORA Core."""
from __future__ import annotations
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from app.config import settings

_CONFIGURED = False

def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    log_path = Path(settings.LOG_FILE).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_path,
        maxBytes=settings.LOG_MAX_BYTES,
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    ))

    for name in ("nora.watch", "nora.watch.commands", "nora.actions"):
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = True

    _CONFIGURED = True
