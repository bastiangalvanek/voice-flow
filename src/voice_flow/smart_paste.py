"""Cmd+V wird zur Kaskade — aber NUR solange das Diktat "frisch" ist.

20.08 Bastian: "wenn ich im AI-Web-Modus Cmd+V druecke, sollen zuerst der Text
und dann die Bilder in Kaskade kommen — geht das mit einmal Cmd+V?"

Es geht, weil Voice Flow weiss, was es selbst zuletzt in die Zwischenablage
gelegt hat. macOS zaehlt jede Aenderung der Zwischenablage mit (changeCount).
Nach der Kaskade merkt sich Voice Flow diesen Zaehlerstand. Ein Cmd+V wird nur
dann uebernommen, wenn der Stand noch derselbe ist — die Zwischenablage also
noch UNSERE Bilder traegt. Kopiert Bastian irgendetwas anderes, springt der
Zaehler weiter und Cmd+V ist sofort wieder zu 100 % das normale Einfuegen.

Die Entscheidung ist reine Logik und voll getestet; das Ablesen des Zaehlers
ist die einzige Systemgrenze.
"""
from __future__ import annotations

import logging
import sys

from voice_flow.target_mode import MODE_AI_WEB

log = logging.getLogger(__name__)


def soll_kaskadieren(mode: str, hat_diktat: bool,
                     stand_jetzt: int | None, stand_gemerkt: int | None,
                     kaskade_laeuft: bool) -> bool:
    """Uebernimmt Voice Flow dieses Cmd+V? Im Zweifel IMMER Nein.

    Ein faelschlich uebernommenes Cmd+V waere der schlimmste Fehler dieses
    Features: "Einfuegen geht auf meinem Mac nicht mehr". Deshalb muss ALLES
    stimmen, sonst laeuft das native Einfuegen unangetastet.
    """
    if kaskade_laeuft:
        # Die Kaskade selbst fuegt per Cmd+V ein — nie das eigene Echo fangen.
        return False
    if mode != MODE_AI_WEB:
        return False
    if not hat_diktat:
        return False
    if stand_gemerkt is None or stand_jetzt is None:
        return False
    return stand_jetzt == stand_gemerkt


def clipboard_stand() -> int | None:
    """Aktueller Aenderungszaehler der macOS-Zwischenablage (None = nicht lesbar)."""
    if sys.platform != "darwin":
        return None
    try:
        from AppKit import NSPasteboard

        return int(NSPasteboard.generalPasteboard().changeCount())
    except Exception as ex:
        log.debug("Zwischenablage-Zaehler nicht lesbar: %s", ex)
        return None
