"""Reine Geometrie + Hit-Test der vertikalen Loom-Werkzeugleiste.

Bewusst OHNE Qt: die Toolbar ist Layout (Buttons untereinander) + Klassifikation
(welcher Button wurde getroffen). Das ist pure Logik und damit unit-getestet, der
Qt-Layer in annotate.py malt die Items nur noch und liest die State-Aenderung ab.
So bleibt annotate.py klein und das Hit-Testing deterministisch pruefbar.
"""
from __future__ import annotations

from dataclasses import dataclass

# 27.06 Bastian: galvanek-orange + Loom-Klassiker rot/gelb/weiss. Reihenfolge =
# Mal-Reihenfolge in der Pille. RGB-Tupel, direkt von Pillow + Qt nutzbar.
PALETTE: list[tuple[int, int, int]] = [
    (240, 115, 32),   # galvanek-orange (Default)
    (255, 69, 58),    # rot
    (255, 214, 64),   # gelb
    (245, 245, 248),  # weiss
]

TOOLBAR_W = 52          # Pillen-Breite
_BTN = 38               # Button-Kantenlaenge
_GAP = 8                # vertikaler Abstand zwischen Buttons
_SEP = 14               # groesserer Abstand vor einer Gruppen-Trennung
_MARGIN_X = 18          # Abstand der Pille vom linken Bildschirmrand
_PAD_Y = 12             # Innen-Polster oben/unten in der Pille


@dataclass(frozen=True)
class ToolbarItem:
    """Ein Button: kind in {tool,color,action}, value = konkrete Wahl."""
    kind: str
    value: object
    x: int
    y: int
    size: int


# (kind, value, separator-davor?) — Reihenfolge von oben nach unten.
_SPEC: list[tuple[str, object, bool]] = [
    ("tool", "pen", False),
    ("tool", "arrow", False),
    ("tool", "rect", False),
]
_SPEC += [("color", i, i == 0) for i in range(len(PALETTE))]
_SPEC += [
    ("action", "undo", True),
    ("action", "clear", False),
    ("action", "shoot", True),
    ("action", "cancel", False),
]


def build_toolbar(viewport_h: int) -> list[ToolbarItem]:
    """Vertikal zentrierte Liste von Buttons fuer eine Viewport-Hoehe.

    Hoehe der Pille aus den Buttons + Separatoren berechnen, dann mittig
    platzieren, dann jedem Button sein y geben. x ist fuer alle gleich (linke
    Pille). Reine Funktion, kein Qt.
    """
    n = len(_SPEC)
    sep_count = sum(1 for _, _, sep in _SPEC if sep)
    content_h = n * _BTN + (n - 1) * _GAP + sep_count * (_SEP - _GAP)
    start_y = max(_PAD_Y, (viewport_h - content_h) // 2)

    x = _MARGIN_X + (TOOLBAR_W - _BTN) // 2
    items: list[ToolbarItem] = []
    y = start_y
    for idx, (kind, value, sep) in enumerate(_SPEC):
        if idx > 0:
            y += (_SEP if sep else _GAP)
        items.append(ToolbarItem(kind=kind, value=value, x=x, y=y, size=_BTN))
        y += _BTN
    return items


def pill_rect(items: list[ToolbarItem]) -> tuple[int, int, int, int]:
    """(left, top, width, height) der dunklen Pille hinter den Buttons."""
    top = min(it.y for it in items) - _PAD_Y
    bottom = max(it.y + it.size for it in items) + _PAD_Y
    return (_MARGIN_X, top, TOOLBAR_W, bottom - top)


def hit_test(point: tuple[int, int], items: list[ToolbarItem]) -> ToolbarItem | None:
    """Welcher Button enthaelt den Klick? None = ausserhalb (also: zeichnen)."""
    px, py = point
    for it in items:
        if it.x <= px < it.x + it.size and it.y <= py < it.y + it.size:
            return it
    return None
