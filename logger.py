"""Centralized logging configuration for AI Investment System."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import BASE_DIR, LOG_LEVEL, LOG_DIR

_initialized = False


def setup_logging(level: str | None = None):
    """Configure the root logger with console and file handlers.

    Args:
        level: Override log level (e.g. "DEBUG", "INFO"). Defaults to config.LOG_LEVEL.
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    log_level = getattr(logging, (level or LOG_LEVEL).upper(), logging.INFO)

    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Console handler (INFO+)
    console = logging.StreamHandler()
    console.setLevel(log_level)
    console.setFormatter(fmt)
    root.addHandler(console)

    # File handler (DEBUG+, rotating 5 MB x 3 backups)
    log_dir = BASE_DIR / LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Suppress noisy third-party loggers
    for name in ("yfinance", "ccxt", "urllib3", "peewee", "matplotlib"):
        logging.getLogger(name).setLevel(logging.WARNING)
