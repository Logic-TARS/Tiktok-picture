from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import DATA_DIR, ensure_data_dirs


LOG_DIR = DATA_DIR / "logs"
APP_LOG_PATH = LOG_DIR / "app.log"
ERROR_LOG_PATH = LOG_DIR / "error.log"


def ensure_log_dir() -> None:
    ensure_data_dirs()
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging() -> None:
    ensure_log_dir()
    root = logging.getLogger()
    if getattr(root, "_tiktok_picture_logging_configured", False):
        return

    root.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    app_handler = RotatingFileHandler(
        APP_LOG_PATH,
        maxBytes=1_048_576,
        backupCount=3,
        encoding="utf-8",
    )
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(formatter)

    error_handler = RotatingFileHandler(
        ERROR_LOG_PATH,
        maxBytes=1_048_576,
        backupCount=3,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    root.addHandler(app_handler)
    root.addHandler(error_handler)
    root.addHandler(console_handler)
    root._tiktok_picture_logging_configured = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)

