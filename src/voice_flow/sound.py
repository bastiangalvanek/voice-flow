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


def _beep(freq: int, duration_ms: int) -> None:
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
