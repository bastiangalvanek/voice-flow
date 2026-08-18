"""Echte SVG-Symbole aus dem Netz statt handgemalter Striche.

18.08 Bastian: "nutze SVG-Icons aus dem Internet, einfach fix downloaden, baue
das ordentlich". Genommen sind Lucide-Icons (ISC-Lizenz) — dieselbe Familie, die
auch Lovable und shadcn benutzen, deshalb passt die Optik.

Die Dateien liegen in assets/icons/. Lucide zeichnet mit stroke="currentColor";
zum Einfaerben wird der Platzhalter vor dem Rendern ersetzt.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_CACHE: dict[tuple[str, str, int], object] = {}


def icon_dir() -> Path:
    """assets/icons — im Entwicklungsbaum wie im gebuendelten Programm."""
    gebundelt = getattr(sys, "_MEIPASS", None)
    if gebundelt:
        return Path(gebundelt) / "assets" / "icons"
    return Path(__file__).resolve().parents[2] / "assets" / "icons"


def load(name: str, farbe: str, groesse: int):
    """Symbol als QPixmap in der gewuenschten Farbe und Kantenlaenge.

    Fehlt die Datei, kommt None zurueck — der Aufrufer malt dann nichts,
    statt mit einer Ausnahme die ganze Leiste zu reissen.
    """
    schluessel = (name, farbe, groesse)
    if schluessel in _CACHE:
        return _CACHE[schluessel]

    pfad = icon_dir() / f"{name}.svg"
    if not pfad.exists():
        log.warning("Symbol %s fehlt (%s)", name, pfad)
        _CACHE[schluessel] = None
        return None

    from PyQt6.QtCore import QByteArray, Qt
    from PyQt6.QtGui import QImage, QPainter, QPixmap
    from PyQt6.QtSvg import QSvgRenderer

    text = pfad.read_text(encoding="utf-8").replace("currentColor", farbe)
    renderer = QSvgRenderer(QByteArray(text.encode("utf-8")))
    if not renderer.isValid():
        log.warning("Symbol %s nicht lesbar", pfad)
        _CACHE[schluessel] = None
        return None

    # Auf dem Retina-Bildschirm doppelt rendern, sonst sind die Linien flau.
    faktor = 2
    bild = QImage(groesse * faktor, groesse * faktor, QImage.Format.Format_ARGB32)
    bild.fill(Qt.GlobalColor.transparent)
    p = QPainter(bild)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(p)
    p.end()

    pix = QPixmap.fromImage(bild)
    pix.setDevicePixelRatio(faktor)
    _CACHE[schluessel] = pix
    return pix
