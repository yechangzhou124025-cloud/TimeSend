from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .paths import log_path


def setup_logging(path: Path | None = None) -> tuple[logging.Logger, Path]:
    destination = path or log_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("DingTalkAutoSend")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(destination, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s.%(msecs)03d | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")
        )
        logger.addHandler(handler)
    return logger, destination
