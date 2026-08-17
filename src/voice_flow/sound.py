from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

_winsound = None
if sys.platform == "win32":
    try:
        import winsound as _ws

        _winsound = _ws
    except ImportError:
        log.debug("winsound nicht verfuegbar — Sound-Feedback deaktiviert.")

# macOS: keine Toene generieren, sondern System-Sounds abspielen (afplay ist
# Bordmittel, non-blocking via Popen). Zuordnung nach Tonhoehe: hoch=Start,
# mittel=Stop, tief=Fehler — gleiche Semantik wie die Windows-Beeps.
_MAC_SOUNDS = [
    (800, "/System/Library/Sounds/Tink.aiff"),   # >=800 Hz: Aufnahme startet
    (500, "/System/Library/Sounds/Pop.aiff"),    # >=500 Hz: Aufnahme stoppt
    (0,   "/System/Library/Sounds/Basso.aiff"),  # tiefer: Fehler
]


def _beep(freq: int, duration_ms: int) -> None:
    if sys.platform == "darwin":
        try:
            import subprocess
            snd = next(p for lo, p in _MAC_SOUNDS if freq >= lo)
            subprocess.Popen(["afplay", snd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as ex:
            log.debug("afplay fehlgeschlagen: %s", ex)
        return
    if _winsound is None:
        return
    try:
        _winsound.Beep(freq, duration_ms)
    except Exception as ex:
        log.debug("winsound.Beep fehlgeschlagen: %s", ex)


def beep_start() -> None:
    """Hoher kurzer Ton — Aufnahme startet."""
    _beep(880, 70)


def beep_stop() -> None:
    """Niedrigerer kurzer Ton — Aufnahme stoppt."""
    _beep(660, 70)


def beep_error() -> None:
    """Tiefer laengerer Ton — Fehler."""
    _beep(220, 220)


def beep_ready() -> None:
    """Zweistufiger aufsteigender Ton — Voice Flow ist startbereit."""
    _beep(660, 80)
    _beep(880, 100)
