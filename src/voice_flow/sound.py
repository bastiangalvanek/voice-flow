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
        log.debug("winsound unavailable — sound feedback disabled.")


def _beep(freq: int, duration_ms: int) -> None:
    if _winsound is None:
        return
    try:
        _winsound.Beep(freq, duration_ms)
    except Exception as ex:
        log.debug("winsound.Beep failed: %s", ex)


def beep_start() -> None:
    """High short tone — recording starts."""
    _beep(880, 70)


def beep_stop() -> None:
    """Lower short tone — recording stops."""
    _beep(660, 70)


def beep_error() -> None:
    """Deep longer tone — error."""
    _beep(220, 220)


def beep_ready() -> None:
    """Two-step ascending tone — Voice Flow is ready."""
    _beep(660, 80)
    _beep(880, 100)
