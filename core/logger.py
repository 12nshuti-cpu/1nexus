"""Centralized logging for NEXUS."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

from config.settings import USER_LOG_DIR

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str = "NEXUS") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    # Ensure log dir
    try:
        USER_LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            USER_LOG_DIR / "nexus.log",
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE))
        logger.addHandler(fh)
    except Exception:
        pass
    # Console handler for dev
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.WARNING)
    ch.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE))
    logger.addHandler(ch)
    logger.propagate = False
    return logger


nexus_log = get_logger("NEXUS")
