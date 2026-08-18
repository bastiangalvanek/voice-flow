"""Farb-Token der Voice-Flow-Oberflaeche.

Eine Quelle fuer Pille, Toasts und Modus-Chip — vorher lagen die Werte nur in
overlay_qt, und der Chip haette sie sonst kopieren muessen (zwei Wahrheiten).
"""
from __future__ import annotations

SURFACE_BASE = "#0B0B0F"
SURFACE_RAISED = "#15151A"
SURFACE_BORDER = "#26262E"
TEXT_PRIMARY = "#F2F2F5"
TEXT_SECONDARY = "#9B9BA3"
TEXT_DIM = "#5C5C66"
ACCENT_REC = "#FF453A"
ACCENT_PROC = "#FFB340"
ACCENT_OK = "#34D399"
GALVANEK_ORANGE = "#F07320"

# Masse der Aufnahme-Pille. Stehen hier, weil sich Zeichen-Leiste und
# Stift-Knopf daran ausrichten (Bastian 18.08: "das soll rechts neben dem
# Aufnahme-Button sein").
PILL_HEIGHT = 34
PILL_RADIUS = 17
PILL_BOTTOM_OFFSET = 24
PILL_WIDTH_RECORDING = 250


def pill_rect_on(viewport_w: int, viewport_h: int,
                 nutzbar_unten: int | None = None) -> tuple[int, int, int, int]:
    """(x, y, w, h) der Aufnahme-Pille auf einem Bildschirm dieser Groesse.

    nutzbar_unten: Unterkante des NUTZBAREN Bereichs (ohne Dock). Die Pille
    richtet sich daran aus, nicht an der vollen Bildschirmhoehe — gemessen
    18.08.: 69 Pixel Unterschied, wodurch die Zeichen-Leiste zeitweise hinter
    dem Dock lag und ihre Knoepfe nicht zu treffen waren.
    """
    unten = viewport_h if nutzbar_unten is None else nutzbar_unten
    x = (viewport_w - PILL_WIDTH_RECORDING) // 2
    y = unten - PILL_HEIGHT - PILL_BOTTOM_OFFSET
    return (x, y, PILL_WIDTH_RECORDING, PILL_HEIGHT)
