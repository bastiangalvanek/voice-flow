from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path.home() / ".voice-flow" / "logs"
LOG_FILE = LOG_DIR / "voice-flow.log"

# 1 MB pro File, 5 Backups → max 6 MB Festplatten-Footprint
MAX_BYTES = 1_000_000
BACKUP_COUNT = 5


def setup_logging(verbose: bool = False) -> Path:
    """Konfiguriert Root-Logger mit Console + Rotating-File-Handler.

    Console zeigt INFO (DEBUG bei --verbose).
    File zeigt immer DEBUG, rotiert bei 1 MB, behaelt 5 Backups.
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

    # Drittanbieter-Libs leiser stellen (verhindert auch API-Key-Leak in DEBUG-Logs)
    for noisy in ("urllib3", "httpx", "httpcore", "openai", "anthropic", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return LOG_FILE
