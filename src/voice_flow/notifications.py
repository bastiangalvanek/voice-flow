"""Premium Toast-Notification-System (SaaS-Stil) fuer Voice Flow.

Zwei getrennte UI-Systeme teilen sich EINEN Qt-Thread (eine QApplication pro
Prozess): die bestehende Recording-Pille (overlay_qt.py) bleibt der persistente
Recording-HUD bottom-center; dieser ToastManager rendert transiente Event-Toasts
top-right auf dem Monitor unter dem Cursor.

Dieses Modul haelt die reine Logik (Kind->Style, Stack-Positionen, Truncation)
und den ToastManager. Das eigentliche QWidget kommt aus notifications_widget.py
(Factory-Pattern wie overlay_qt._build_qt_class, damit kein Top-Level-Qt-Import).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class ToastKind(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    ERROR = "error"
    RECORDING = "recording"
    SCREENSHOT = "screenshot"
    TRANSCRIPT = "transcript"
    DUMP = "dump"


@dataclass
class ToastSpec:
    kind: ToastKind
    title: str
    subtitle: str = ""
    thumbnail_path: str | None = None
    # (label, callback) je Action-Button. Leer = reiner Info-Toast (click-through).
    actions: list[tuple[str, Callable[[], None]]] = field(default_factory=list)
    duration_ms: int = 4000


# Accent-Farben aus denselben Tokens wie die Pille (overlay_qt.py) — Pille + Toasts
# wie aus einer Hand. icon = vektorgemalter Glyph im Widget-paintEvent.
_STYLE = {
    ToastKind.INFO:       {"accent": "#9B9BA3", "icon": "info"},
    ToastKind.SUCCESS:    {"accent": "#34D399", "icon": "check"},
    ToastKind.ERROR:      {"accent": "#FF453A", "icon": "warn"},
    ToastKind.RECORDING:  {"accent": "#FF453A", "icon": "rec"},
    ToastKind.SCREENSHOT: {"accent": "#F07320", "icon": "cam"},
    ToastKind.TRANSCRIPT: {"accent": "#FFB340", "icon": "text"},
    ToastKind.DUMP:       {"accent": "#34D399", "icon": "paste"},
}


def style_for(kind: ToastKind) -> dict:
    """Accent-Farbe + Icon-Key fuer eine Toast-Art."""
    return _STYLE.get(kind, _STYLE[ToastKind.INFO])


def truncate(text: str, n: int) -> str:
    """Einzeiler, hart auf n Zeichen + Ellipsis."""
    text = text.replace("\n", " ").strip()
    return text if len(text) <= n else text[:n] + "…"


def stack_positions(
    heights: list[int],
    screen: tuple[int, int, int, int],
    margin: int,
    gap: int,
    width: int,
) -> list[tuple[int, int]]:
    """Top-right Stack, Reihenfolge = Eingabe-Reihenfolge (neuester zuerst = oben).

    `heights` = Hoehe je Toast (variabel, je nach Subtitle/Actions). screen =
    (x, y, w, h) der availableGeometry des Ziel-Monitors. Rechtsbuendig mit
    `margin` Abstand zur Kante, vertikaler Abstand `gap` zwischen Toasts.
    """
    sx, sy, sw, sh = screen
    x = sx + sw - width - margin
    out: list[tuple[int, int]] = []
    y = sy + margin
    for h in heights:
        out.append((x, y))
        y += h + gap
    return out
