"""Recording-Backup: WAV-Dateien werden auf Disk gesichert bevor Whisper
transkribiert. Bei API-Fehler / Crash / Disconnect bleibt das Audio erhalten.

Speicherort: ~/.voice-flow/recordings/recording_<timestamp>.wav

Lebenszyklus:
  1. Pipeline ruft `save_recording(wav_bytes)` → liefert Path zurueck
  2. Transkription laeuft (Whisper)
  3. Erfolg → `delete_recording(path)` raeumt auf
  4. Fehler → File bleibt, log warning mit Pfad. User kann manuell handhaben.

Auto-Cleanup beim Voice-Flow-Start:
  - recordings aelter als RETENTION_DAYS werden automatisch geloescht
  - verhindert dass Disk unbegrenzt voll laeuft

Bekanntes Limit:
  - OpenAI Whisper API: 25 MB max pro Request
  - 8 min × 16 kHz × mono × int16 ≈ 15 MB → fits easy
  - 14 min × 16 kHz × mono × int16 ≈ 27 MB → exceed (raise warning)
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

RECORDINGS_DIR = Path.home() / ".voice-flow" / "recordings"
RETENTION_DAYS = 7
WHISPER_MAX_BYTES = 25 * 1024 * 1024  # 25 MB OpenAI-Limit
WHISPER_WARN_BYTES = 22 * 1024 * 1024  # warn ab 22 MB (zerbrechlich nahe Limit)


def save_recording(wav_bytes: bytes, suffix: str = "") -> Path:
    """Speichert WAV als Datei mit Timestamp. Returns Pfad.

    suffix: optionaler Marker (z.B. "_failed", "_pending").
    """
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # ms precision
    fname = f"recording_{ts}{suffix}.wav"
    path = RECORDINGS_DIR / fname
    path.write_bytes(wav_bytes)
    size_kb = len(wav_bytes) // 1024
    log.debug("Recording saved: %s (%d KB)", path.name, size_kb)
    return path


def delete_recording(path: Path) -> None:
    """Loescht ein Backup nach erfolgreicher Transkription."""
    if path is None:
        return
    try:
        path.unlink()
        log.debug("Recording deleted: %s", path.name)
    except FileNotFoundError:
        pass
    except Exception as ex:
        log.warning("Konnte Recording nicht loeschen (%s): %s", path, ex)


def mark_failed(path: Path) -> Path:
    """Renamed ein Recording mit _failed-Suffix damit User es sieht.

    Wenn rename fehlschlaegt: Original-Pfad bleibt erhalten.
    """
    if path is None or not path.exists():
        return path
    new_name = path.stem + "_failed" + path.suffix
    new_path = path.with_name(new_name)
    try:
        path.rename(new_path)
        log.info("Recording markiert als FAILED: %s", new_path.name)
        return new_path
    except Exception as ex:
        log.warning("Konnte Recording nicht renamen (%s): %s", path, ex)
        return path


def cleanup_old_recordings(max_age_days: int = RETENTION_DAYS) -> int:
    """Loescht recordings aelter als max_age_days.

    Wird bei Voice-Flow-Start aufgerufen. Returns count of deleted files.
    """
    if not RECORDINGS_DIR.exists():
        return 0
    cutoff = datetime.now().timestamp() - max_age_days * 86400
    count = 0
    for f in RECORDINGS_DIR.glob("recording_*.wav"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                count += 1
        except Exception as ex:
            log.debug("Cleanup skip %s: %s", f, ex)
    if count > 0:
        log.info("Cleanup: %d alte Recordings (>%dd) geloescht.", count, max_age_days)
    return count


def list_pending_recordings() -> list[Path]:
    """Listet recordings — sowohl normal als auch _failed-markierte.

    Wird bei Voice-Flow-Start fuer User-Info benutzt.
    """
    if not RECORDINGS_DIR.exists():
        return []
    return sorted(RECORDINGS_DIR.glob("recording_*.wav"))


def check_size_for_whisper(wav_bytes: bytes) -> tuple[bool, str]:
    """Prueft ob audio in OpenAI's 25-MB-Limit passt.

    Returns (ok, message). Wenn ok=False: ist > 25 MB, API wird ablehnen.
    Wenn ok=True und size > warn-threshold: warning-message setzt aber kein block.
    """
    size = len(wav_bytes)
    if size > WHISPER_MAX_BYTES:
        return False, (
            f"Audio {size // 1024 // 1024} MB ueberschreitet Whisper-Limit (25 MB). "
            f"Aufnahme zu lang. Datei wird trotzdem gesichert."
        )
    if size > WHISPER_WARN_BYTES:
        return True, f"Audio {size // 1024 // 1024} MB nahe am 25-MB-Limit."
    return True, ""
