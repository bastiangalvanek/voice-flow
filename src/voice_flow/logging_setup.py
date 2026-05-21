from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path.home() / ".voice-flow" / "logs"
LOG_FILE = LOG_DIR / "voice-flow.log"

# 1 MB per file, 5 backups → max 6 MB disk footprint.
MAX_BYTES = 1_000_000
BACKUP_COUNT = 5


def setup_logging(verbose: bool = False) -> Path:
    """Configure root logger with console + rotating-file handler.

    Console shows INFO (DEBUG with --verbose).
    File always shows DEBUG, rotates at 1 MB, keeps 5 backups.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    console_level = logging.DEBUG if verbose else logging.INFO

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)-30s | %(message)s",
        datefmt="%H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for h in list(root.handlers):
        root.removeHandler(h)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(console_level)
    console.setFormatter(fmt)
    root.addHandler(console)

    file_h = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_h.setLevel(logging.DEBUG)
    file_h.setFormatter(fmt)
    root.addHandler(file_h)

    # Quiet noisy libraries — also prevents API-key leak in DEBUG logs.
    for noisy in ("urllib3", "httpx", "httpcore", "openai", "anthropic", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return LOG_FILE
