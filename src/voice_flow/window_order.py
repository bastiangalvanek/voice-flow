"""Ein Fenster nach VORNE legen, ohne die App zu aktivieren (macOS).

GEMESSEN 20.08.2026 (Qt 6.11, macOS 15): `QWidget.raise_()` holt auf dem Mac
die ganze App nach vorne — auch bei einem Qt.Tool-Fenster mit
WA_ShowWithoutActivating. `show()` allein tut das NICHT.

    Ausgangslage (Hauptfenster minimiert) -> vorne: Finder
    nach pille.show()                     -> vorne: Finder
    nach chip.show()+raise_()             -> vorne: python   <-- Fokus geklaut
    nach pille.hide()+show()              -> vorne: Finder

Folge im Betrieb: F5 zeigt die Pille, die Pille platziert Chip und Stift, deren
`raise_()` aktiviert Voice Flow — der Fokus springt aus Bastians Fenster weg und
macOS klappt dabei das minimierte Voice-Flow-Fenster wieder auf.

`[NSWindow orderFront:]` macht dasselbe fuer die Reihenfolge, ohne zu
aktivieren (in derselben Messreihe gegengeprueft: vorne blieb Finder).
"""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)


def nach_vorne(widget) -> bool:
    """Widget ueber die Geschwister legen. True = ohne Aktivierung erledigt.

    Auf Windows gibt es das Problem nicht, dort bleibt raise_() richtig.
    """
    if sys.platform == "darwin":
        try:
            import objc

            view = objc.objc_object(c_void_p=int(widget.winId()))
            fenster = view.window()
            if fenster is not None:
                fenster.orderFront_(None)
                return True
        except Exception as ex:  # pragma: no cover — Systemgrenze
            log.debug("orderFront nicht moeglich (%s) — falle auf raise_ zurueck.", ex)
    widget.raise_()
    return False
