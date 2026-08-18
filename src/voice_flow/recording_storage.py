"""Recording-Storage: JEDE Aufnahme ueberlebt auf Disk — nichts geht mehr verloren.

Speicherort: ~/.voice-flow/recordings/

Lebenszyklus (11.07 Bastian "die sollten wir immer storen"):
  1. Pipeline ruft `save_recording(wav_bytes)` → liefert Path zurueck
  2. Transkription laeuft (Whisper)
  3. Erfolg → `archive_recording(path)`: WAV → winziges OGG/Opus-Archiv
     (~1 MB / 10 min) statt Hard-Delete. Frueher wurde hier geloescht →
     ein einziger Downstream-Fehler (Halluzination, Paste in falsches
     Fenster) und das Audio war unwiederbringlich weg (SSD-TRIM).
  4. Fehler → WAV bleibt mit _failed/_suspect-Marker liegen.
     Nach-Transkription: `python -m voice_flow.recover` → _recovered.

Auto-Cleanup beim Voice-Flow-Start (Retention, kein Endlos-Wachstum):
  - alles aelter als RETENTION_DAYS wird geloescht
  - danach Groessen-Deckel MAX_TOTAL_BYTES: aelteste zuerst raus
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

RECORDINGS_DIR = Path.home() / ".voice-flow" / "recordings"
# 16.08.2026 Bastian: "mp3 dateien laenger liegen lassen damit man immer recovern
# kann". Ein Diktat ist oft erst Tage spaeter als luecken- oder fehlerhaft erkannt —
# 30 Tage waren dafuer zu kurz. Opus-Archive kosten ~1 MB / 10 min, ein Jahr taeglicher
# Nutzung passt locker unter den Deckel. Beides per .env uebersteuerbar.
RETENTION_DAYS = int(os.getenv("VOICE_FLOW_RETENTION_DAYS", "365"))
MAX_TOTAL_BYTES = int(
    os.getenv("VOICE_FLOW_MAX_ARCHIVE_MB", "5000")
) * 1024 * 1024  # Groessen-Deckel ueber alle Archive/Backups


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


def archive_recording(path: Path) -> Path | None:
    """Nach erfolgreicher Transkription: WAV → OGG/Opus-Archiv, WAV loeschen.

    Opus ist fuer Sprache verlustarm genug fuer jeden Re-Transcribe (bewiesen
    28.06: identische Whisper-Ergebnisse) und ~10x kleiner. Schlaegt das
    Encoding fehl, bleibt die WAV selbst das Archiv — nie Audio verlieren,
    nur um Platz zu sparen. Returns Archiv-Pfad (ogg oder wav), None wenn
    das File weg ist.
    """
    if path is None or not path.exists():
        return None
    from voice_flow.audio_encode import to_opus

    ogg_path = path.with_suffix(".ogg")
    try:
        opus = to_opus(path.read_bytes())
        if opus:
            ogg_path.write_bytes(opus)
            path.unlink()
            log.debug("Recording archiviert: %s (%d KB)", ogg_path.name, len(opus) // 1024)
            return ogg_path
    except Exception as ex:  # noqa: BLE001 - Archivieren darf nie Audio kosten
        log.warning("Archivieren fehlgeschlagen (%s) — WAV bleibt: %s", path.name, ex)
    # Opus nicht moeglich → WAV selbst ist das Archiv. _archived-Marker, damit
    # sie weder als "pending" alarmiert noch vor der Retention geschuetzt wird
    # (Critic P2: sonst falscher Pending-Alarm bei jedem Start).
    archived = path.with_name(path.stem + "_archived" + path.suffix)
    try:
        path.rename(archived)
        return archived
    except Exception as ex:  # noqa: BLE001 - Rename ist Kosmetik, Audio liegt sicher
        log.warning("Konnte %s nicht als archived markieren: %s", path.name, ex)
        return path


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


def mark_suspect(path: Path) -> Path:
    """Renamed ein Recording mit _suspect-Suffix statt es zu loeschen.

    Aufruf wenn die Transkription nach einer Halluzination aussah (kaum Worte /
    falsche Sprache): das Audio wird fuer einen manuellen Retry behalten, statt
    wie bei "Erfolg" geloescht zu werden. Rename-Fehler → Original-Pfad bleibt.
    """
    if path is None or not path.exists():
        return path
    new_name = path.stem + "_suspect" + path.suffix
    new_path = path.with_name(new_name)
    try:
        path.rename(new_path)
        log.warning("Recording BEHALTEN (verdaechtige Transkription): %s", new_path.name)
        return new_path
    except Exception as ex:
        log.warning("Konnte Recording nicht als suspect renamen (%s): %s", path, ex)
        return path


def _is_open_work(f: Path) -> bool:
    """WAVs ohne _recovered/_archived-Marker = noch nicht transkribiertes Audio.

    Das schliesst `_partial.wav` (Live-Mitschrift eines eingefrorenen oder
    abgeschossenen Laufs, siehe spool.py) bewusst mit ein: sie ist dann die
    einzige Kopie und muss die Retention ueberleben.

    Genau diese Dateien sind der Grund fuer das ganze Storage-Feature — sie
    sind fuer die Retention TABU (Critic P1: der Groessen-Deckel haette sonst
    zuerst die aeltesten+groessten Files geopfert, und das sind exakt die
    un-recoverten _failed-WAVs).
    """
    return f.suffix.lower() == ".wav" and not (
        f.stem.endswith("_recovered") or f.stem.endswith("_archived")
    )


def cleanup_old_recordings(
    max_age_days: int = RETENTION_DAYS, max_total_bytes: int = MAX_TOTAL_BYTES
) -> int:
    """Retention: erst Alters-Cutoff, dann Groessen-Deckel (aelteste zuerst).

    Greift NUR auf Erledigtes: .ogg-Archive, _recovered/_archived-WAVs und
    Recover-Texte (.txt). Un-recovertes Audio (plain/_failed/_suspect-WAVs)
    wird NIE automatisch geloescht — nichts geht verloren, bis der User es
    recovert hat. Wird bei Voice-Flow-Start aufgerufen. Returns Anzahl
    geloeschter Files.
    """
    if not RECORDINGS_DIR.exists():
        return 0
    cutoff = datetime.now().timestamp() - max_age_days * 86400
    count = 0
    survivors: list[tuple[float, int, Path]] = []  # (mtime, size, path)
    for f in sorted(RECORDINGS_DIR.glob("recording_*.*")):
        if f.suffix.lower() not in (".wav", ".ogg", ".txt"):
            continue
        if _is_open_work(f):
            continue
        try:
            st = f.stat()
            if st.st_mtime < cutoff:
                f.unlink()
                count += 1
            else:
                survivors.append((st.st_mtime, st.st_size, f))
        except Exception as ex:
            log.debug("Cleanup skip %s: %s", f, ex)
    if count > 0:
        log.info("Cleanup: %d alte Recordings (>%dd) geloescht.", count, max_age_days)

    # Groessen-Deckel: aelteste zuerst opfern bis der Rest unter den Deckel passt.
    total = sum(size for _, size, _ in survivors)
    if total > max_total_bytes:
        for _, size, f in sorted(survivors):
            if total <= max_total_bytes:
                break
            try:
                f.unlink()
                total -= size
                count += 1
                log.info("Cleanup (Deckel %d MB): %s geloescht.", max_total_bytes // 1024 // 1024, f.name)
            except Exception as ex:
                log.debug("Cleanup skip %s: %s", f, ex)
    return count


def list_pending_recordings() -> list[Path]:
    """WAVs die noch Aufmerksamkeit brauchen (plain/_failed/_suspect).

    _recovered/_archived und .ogg-Archive sind erledigt, zaehlen nicht als
    pending. Wird bei Voice-Flow-Start fuer User-Info benutzt.
    """
    if not RECORDINGS_DIR.exists():
        return []
    return sorted(p for p in RECORDINGS_DIR.glob("recording_*.wav") if _is_open_work(p))


# 16 kHz, 16 bit, mono = 32 KB Ton pro Sekunde. Alles unter anderthalb Sekunden
# ist ein Fehlstart (Taste zweimal getippt) und enthaelt nie Sprache.
MINDESTGROESSE_BYTES = 48 * 1024


def list_pending_with_audio() -> list[Path]:
    """Liegengebliebene Aufnahmen, in denen ueberhaupt Ton steckt.

    EINE Quelle fuer beide Anzeigen (Hinweis beim Start und Zeile im Fenster) —
    sonst nennen die beiden verschiedene Zahlen fuer dieselbe Sache
    (gemessen 19.08.: 15 im Hinweis, 12 im Fenster).
    Geloescht wird nichts; Fehlstarts bleiben liegen, sie werden nur nicht
    als "Transkript fehlt" gezaehlt.
    """
    behalten = []
    for pfad in list_pending_recordings():
        try:
            if pfad.stat().st_size >= MINDESTGROESSE_BYTES:
                behalten.append(pfad)
        except OSError:
            continue
    return behalten
