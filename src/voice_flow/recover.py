"""Recovery-CLI: liegengebliebene Aufnahmen nachträglich transkribieren.

    .venv\\Scripts\\python.exe -m voice_flow.recover              # alle _failed/_suspect
    .venv\\Scripts\\python.exe -m voice_flow.recover pfad\\zu.wav  # gezielt

Warum (11.07 Bastian): Ein 14.5-Min-Diktat scheiterte am (falschen) 25-MB-
Pre-Check; die WAV lag gesichert in ~/.voice-flow/recordings/, aber es gab
kein Werkzeug, sie durch die Pipeline zu ziehen. Jetzt: gleicher Transcriber
wie die App (inkl. Lang-Audio-Chunking, Opus, Hedging, Retry), Ergebnis geht
in die Transkript-History + als .txt neben die Aufnahme + ins Clipboard.
Erfolgreich recoverte Dateien werden `_recovered` markiert (nicht gelöscht —
die Retention in recording_storage räumt sie zeitgesteuert ab).
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from voice_flow.audio_chunks import wav_duration_seconds
from voice_flow.config import load_config
from voice_flow.recording_storage import RECORDINGS_DIR, list_pending_recordings
from voice_flow.transcript_history import append_transcript
from voice_flow.transcript_quality import is_suspect_transcription
from voice_flow.transcription import Transcriber

log = logging.getLogger(__name__)

RECOVERABLE_SUFFIXES = ("_failed", "_suspect")


def find_recoverable() -> list[Path]:
    """Alle offenen WAVs im Recordings-Ordner, älteste zuerst.

    Auch PLAIN recording_*.wav (Crash zwischen save_recording und
    mark_failed) zählen — genau die soll recover retten (Critic P2).
    """
    return list_pending_recordings()


def mark_recovered(path: Path) -> Path:
    """`_failed`/`_suspect` → `_recovered`. Rename-Fehler lassen das File liegen."""
    stem = path.stem
    for s in RECOVERABLE_SUFFIXES:
        if stem.endswith(s):
            stem = stem[: -len(s)]
            break
    new_path = path.with_name(stem + "_recovered" + path.suffix)
    try:
        path.rename(new_path)
        return new_path
    except Exception as ex:  # noqa: BLE001 - Recovery-Erfolg zählt, Rename ist Kosmetik
        log.warning("Konnte %s nicht als recovered markieren: %s", path.name, ex)
        return path


def recover_file(path: Path, transcriber: Transcriber, language: str) -> str:
    """Eine WAV transkribieren, persistieren, markieren. Returns Transkript."""
    wav_bytes = path.read_bytes()
    duration = wav_duration_seconds(wav_bytes)
    log.info("RECOVER  %s (%.1f min) …", path.name, duration / 60.0)
    t0 = time.time()
    text = transcriber.transcribe(wav_bytes, language=language)
    elapsed = time.time() - t0
    if not text:
        log.warning("RECOVER  %s: leeres Transkript — Datei bleibt unverändert.", path.name)
        return ""

    word_count = len(text.split())
    suspect, reason = is_suspect_transcription(text, duration)
    if suspect:
        # Wahrscheinlich halluziniert: .txt zum Begutachten, aber KEIN
        # History-Eintrag (sonst haeuft jeder erneute Lauf Duplikate an,
        # Critic P2) und die Datei bleibt unmarkiert fuer den Retry.
        path.with_suffix(".txt").write_text(text, encoding="utf-8")
        log.warning("RECOVER  Transkript verdächtig (%s) — Datei bleibt für Retry.", reason)
        return text

    # Erst renamen, dann .txt schreiben — so heissen WAV und TXT gleich
    # (recording_x_recovered.wav + recording_x_recovered.txt).
    path = mark_recovered(path)
    txt_path = path.with_suffix(".txt")
    txt_path.write_text(text, encoding="utf-8")
    append_transcript(
        text=text,
        duration_sec=duration,
        word_count=word_count,
        model=transcriber.model,
        pipeline_ms=int(elapsed * 1000),
    )
    log.info(
        "RECOVER  ✓ %d Worte in %.1fs → %s (+ History + Clipboard)",
        word_count,
        elapsed,
        txt_path.name,
    )
    return text


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    args = list(sys.argv[1:] if argv is None else argv)

    targets = [Path(a) for a in args] if args else find_recoverable()
    if not targets:
        print("Nichts zu recovern: keine _failed/_suspect-Aufnahmen in", RECORDINGS_DIR)
        return 0
    missing = [p for p in targets if not p.exists()]
    if missing:
        for p in missing:
            print("Datei nicht gefunden:", p)
        return 2

    config = load_config()
    transcriber = Transcriber(api_key=config.openai_api_key, model=config.whisper_model)

    last_text = ""
    failures = 0
    for path in targets:
        try:
            text = recover_file(path, transcriber, config.language)
        except Exception as ex:  # noqa: BLE001 - eine kaputte Datei killt nicht den Rest
            log.error("RECOVER  %s fehlgeschlagen: %s", path.name, ex)
            failures += 1
            continue
        if text:
            last_text = text
            print(f"\n===== {path.name} =====\n{text}\n")

    if last_text:
        try:
            import pyperclip

            pyperclip.copy(last_text)
        except Exception as ex:  # noqa: BLE001 - Clipboard ist Komfort, kein Muss
            log.warning("Clipboard nicht beschreibbar: %s", ex)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
