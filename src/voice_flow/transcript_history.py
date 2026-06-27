"""Persistent History aller transkribierten Diktate.

Bei jedem erfolgreichen Diktat wird der Text in zwei Formate gespeichert:

  ~/.voice-flow/transcripts/transcripts.jsonl   (strukturiert, eine Zeile pro Eintrag)
  ~/.voice-flow/transcripts/transcripts.txt     (human-readable, gruppiert pro Tag)

So findest du spaeter immer wieder was du gesagt hast — auch wenn der Paste in
der Ziel-App schiefging oder du den Text nochmal brauchst.

Wird bei `paste ✓` aufgerufen. Fehler beim Schreiben werden nur geloggt, blocken
die Pipeline NICHT (Diktieren funktioniert weiter auch wenn History kaputt ist).
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
    """Append einen History-Eintrag (jsonl + txt).

    Fehler werden geloggt aber nicht raised — History darf die Pipeline nicht killen.
    """
    if not text or not text.strip():
        return

    try:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as ex:
        log.warning("History-Dir kann nicht angelegt werden (%s): %s", HISTORY_DIR, ex)
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

    # JSONL — strukturiert (eine Zeile pro Eintrag, parsbar)
    try:
        with open(JSONL_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as ex:
        log.warning("History JSONL append fehlgeschlagen: %s", ex)

    # TXT — human-readable mit Day-Header
    try:
        needs_day_header = _needs_day_header(date_human)
        with open(TXT_FILE, "a", encoding="utf-8") as f:
            if needs_day_header:
                f.write(f"\n========== {date_human} ==========\n\n")
            meta = f"{word_count} Wort" if word_count == 1 else f"{word_count} Woerter"
            f.write(f"[{ts_human}]  {meta} · {duration_sec:.1f}s audio\n")
            f.write(f"{text}\n\n")
    except Exception as ex:
        log.warning("History TXT append fehlgeschlagen: %s", ex)


def _needs_day_header(date_str: str) -> bool:
    """True wenn die TXT-File noch keinen Eintrag fuer date_str hat.

    Schaut auf die letzte nicht-leere Zeile im File — wenn der dortige Day-Header
    nicht matched, schreibt der Caller einen neuen. Bei FileNotFoundError: ja, neuer Tag.
    """
    if not TXT_FILE.exists():
        return True
    try:
        # Effizienter Tail-Read: max 4 KB vom Ende lesen
        size = TXT_FILE.stat().st_size
        with open(TXT_FILE, "rb") as f:
            f.seek(max(0, size - 4096))
            tail = f.read().decode("utf-8", errors="replace")
        return f"========== {date_str} ==========" not in tail
    except Exception:
        return False


def get_history_paths() -> dict[str, Path]:
    """Returns die History-Pfade — fuer Tray-Menu "Open History" o.ae."""
    return {
        "jsonl": JSONL_FILE,
        "txt": TXT_FILE,
        "dir": HISTORY_DIR,
    }


def open_history_in_explorer() -> bool:
    """Oeffnet den History-Ordner im File-Explorer. Returns True bei Erfolg."""
    if not HISTORY_DIR.exists():
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.startfile(str(HISTORY_DIR))  # Windows-only — passt fuer Voice Flow
        return True
    except Exception as ex:
        log.warning("Konnte History-Ordner nicht oeffnen: %s", ex)
        return False
