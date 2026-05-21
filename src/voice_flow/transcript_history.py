"""Persistent history of all transcribed dictations.

Each successful dictation is saved in two formats:

  ~/.voice-flow/transcripts/transcripts.jsonl   (structured, one line per entry)
  ~/.voice-flow/transcripts/transcripts.txt     (human-readable, grouped per day)

Errors writing history are logged but do NOT block the pipeline — dictation
continues to work even if history is broken.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

HISTORY_DIR = Path.home() / ".voice-flow" / "transcripts"
JSONL_FILE = HISTORY_DIR / "transcripts.jsonl"
TXT_FILE = HISTORY_DIR / "transcripts.txt"


def append_transcript(
    text: str,
    duration_sec: float = 0.0,
    word_count: int = 0,
    model: str = "",
    pipeline_ms: int = 0,
) -> None:
    """Append a history entry (jsonl + txt)."""
    if not text or not text.strip():
        return

    try:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as ex:
        log.warning("History dir could not be created (%s): %s", HISTORY_DIR, ex)
        return

    now = datetime.now()
    ts_iso = now.isoformat(timespec="seconds")
    ts_human = now.strftime("%H:%M:%S")
    date_human = now.strftime("%Y-%m-%d")

    entry = {
        "timestamp": ts_iso,
        "text": text,
        "duration_sec": round(duration_sec, 2),
        "word_count": word_count,
        "model": model,
        "pipeline_ms": pipeline_ms,
    }

    try:
        with open(JSONL_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as ex:
        log.warning("History JSONL append failed: %s", ex)

    try:
        needs_day_header = _needs_day_header(date_human)
        with open(TXT_FILE, "a", encoding="utf-8") as f:
            if needs_day_header:
                f.write(f"\n========== {date_human} ==========\n\n")
            meta = f"{word_count} word" if word_count == 1 else f"{word_count} words"
            f.write(f"[{ts_human}]  {meta} · {duration_sec:.1f}s audio\n")
            f.write(f"{text}\n\n")
    except Exception as ex:
        log.warning("History TXT append failed: %s", ex)


def _needs_day_header(date_str: str) -> bool:
    """True if the TXT file has no entry for date_str yet."""
    if not TXT_FILE.exists():
        return True
    try:
        size = TXT_FILE.stat().st_size
        with open(TXT_FILE, "rb") as f:
            f.seek(max(0, size - 4096))
            tail = f.read().decode("utf-8", errors="replace")
        return f"========== {date_str} ==========" not in tail
    except Exception:
        return False


def get_history_paths() -> dict[str, Path]:
    """History paths — for tray menu "Open History" etc."""
    return {
        "jsonl": JSONL_FILE,
        "txt": TXT_FILE,
        "dir": HISTORY_DIR,
    }


def open_history_in_explorer() -> bool:
    """Open the history folder in File Explorer. Returns True on success."""
    if not HISTORY_DIR.exists():
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.startfile(str(HISTORY_DIR))  # Windows only
        return True
    except Exception as ex:
        log.warning("Could not open history folder: %s", ex)
        return False
