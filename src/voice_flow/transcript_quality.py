"""Heuristik: sieht eine Whisper-Ausgabe nach einer Halluzination aus?

Reine Logik, keine I/O — voll testbar. Zweck: eine kaputte Transkription (z.B.
Bluetooth-Mikro liefert im 8-kHz-Hands-Free-Modus verwaschenes Audio → Whisper
haengt eine kurze Phrase in falscher Sprache raus, "This will be the first time.")
erkennen, damit die Pipeline die Original-Aufnahme NICHT loescht, sondern fuer
einen erneuten Versuch behaelt. Realfall 07.07.2026: 266s Audio → 12 Worte
Englisch, Aufnahme geloescht, 4.5 min unwiederbringlich weg.

Bewusst hoch-praezise: lieber eine echte Halluzination durchlassen als eine gute
Transkription faelschlich als verdaechtig markieren. Nur wer WEIT unter normaler
Sprechdichte liegt, gilt als verdaechtig.
"""
from __future__ import annotations

# Normale Sprechdichte liegt bei ~2-3 Woertern/Sekunde. Alles darunter bei
# nennenswerter Laenge ist praktisch sicher kaputt (Realfall: 12/266 = 0.045 W/s
# — ~50x zu wenig). 0.5 laesst selbst sehr langsames/pausenreiches Diktat durch.
MIN_WORDS_PER_SEC = 0.5
# Kurze Schnipsel nicht bewerten — zu wenig Signal, und ein 3-Sekunden-"ja, genau"
# hat legitim wenige Worte.
MIN_DURATION_SEC = 8.0


def is_suspect_transcription(text: str, duration_sec: float) -> tuple[bool, str]:
    """Gibt (verdaechtig, grund) zurueck. Nur bei starkem Signal True."""
    if duration_sec < MIN_DURATION_SEC:
        return False, ""
    n_words = len((text or "").split())
    wps = n_words / duration_sec if duration_sec > 0 else 0.0
    if wps < MIN_WORDS_PER_SEC:
        return True, (
            f"nur {n_words} Worte fuer {duration_sec:.0f}s Audio "
            f"({wps:.2f} W/s statt normal ~2-3) — Aufnahme wohl verzerrt (Mikro?)"
        )
    return False, ""
