"""Qt-Rendering der Zeichen-Leiste im Lovable-Stil.

18.08 Bastian: "1:1 wie bei Lovable, auch vom UX-Gefuehl". Das heisst hier:
dunkle schwebende Leiste, der aktive Stift-Knopf mit lila Ring und Beschriftung
"Annotation", danach Zurueck, Vor und "Clear" als Text — ausgegraut, solange
nichts gezeichnet ist. Beim Ueberfahren hellt der Knopf leicht auf.

Reine Mal-Logik, keine Zustandsaenderung. Die Qt-Klassen kommen per Bundle rein
(Factory-Muster wie im Rest des Projekts).
"""
from __future__ import annotations

from voice_flow.annotate_toolbar import ToolbarItem, is_enabled, pill_rect
from voice_flow.icons import load as load_icon

# Farben aus Lovables Leiste abgelesen.
BAR_BG = (22, 22, 27, 242)
BAR_BORDER = (255, 255, 255, 20)
ACTIVE_RING = (124, 106, 255)      # lila wie Lovables aktiver Annotation-Knopf
ACTIVE_TEXT = (240, 240, 245)
IDLE_TEXT = (205, 205, 214)
DISABLED_TEXT = (255, 255, 255, 70)
HOVER_FILL = (255, 255, 255, 22)


def paint_toolbar(p, items: list[ToolbarItem], active_tool: str,
                  qt, hat_striche: bool = True, hover_value=None,
                  hat_zurueckgenommenes: bool = False) -> None:
    """Malt die Leiste samt Knoepfen.

    hat_striche: steuert die ausgegrauten Knoepfe (Zurueck/Vor/Clear).
    hover_value: value des Knopfes unter der Maus, oder None.
    """
    QColor, QPen, QPainterPath, QRectF = qt.QColor, qt.QPen, qt.QPainterPath, qt.QRectF
    left, top, w, h = pill_rect(items)
    leiste = QPainterPath()
    leiste.addRoundedRect(QRectF(left, top, w, h), h / 2, h / 2)
    p.fillPath(leiste, QColor(*BAR_BG))
    p.setPen(QPen(QColor(*BAR_BORDER), 1))
    p.drawPath(leiste)

    for it in items:
        aktiv = it.kind == "tool" and it.value == active_tool
        an = is_enabled(it, hat_striche, hat_zurueckgenommenes)
        _paint_button(p, it, aktiv=aktiv, enabled=an,
                      hover=(hover_value is not None and it.value == hover_value and an),
                      qt=qt)


def _paint_button(p, it: ToolbarItem, aktiv: bool, enabled: bool, hover: bool, qt) -> None:
    QColor, QPen, QRectF, QPainterPath = qt.QColor, qt.QPen, qt.QRectF, qt.QPainterPath
    Qt = qt.Qt

    if hover and not aktiv:
        fl = QPainterPath()
        fl.addRoundedRect(QRectF(it.x, it.y, it.width, it.height), 8, 8)
        p.fillPath(fl, QColor(*HOVER_FILL))

    if aktiv:
        ring = QPainterPath()
        ring.addRoundedRect(QRectF(it.x + 0.5, it.y + 0.5, it.width - 1, it.height - 1), 8, 8)
        p.fillPath(ring, QColor(124, 106, 255, 34))
        p.setPen(QPen(QColor(*ACTIVE_RING), 1.4))
        p.drawPath(ring)

    if enabled:
        farbe = QColor(*ACTIVE_TEXT) if aktiv else QColor(*IDLE_TEXT)
    else:
        farbe = QColor(*DISABLED_TEXT)

    stift = QPen(farbe, 1.8)
    stift.setCapStyle(Qt.PenCapStyle.RoundCap)
    stift.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(stift)
    p.setBrush(Qt.BrushStyle.NoBrush)

    x = it.x + (14 if it.label else it.width / 2 - 0)
    cy = it.y + it.height / 2
    if it.icon:
        cx = (it.x + 18) if it.label else (it.x + it.width / 2)
        _paint_icon(p, it.icon, cx, cy, farbe, qt)
        x = cx + 14

    if it.label:
        schrift = p.font()
        schrift.setPointSizeF(11.5)
        schrift.setWeight(qt.QFont.Weight.DemiBold if aktiv else qt.QFont.Weight.Medium)
        p.setFont(schrift)
        p.setPen(QPen(farbe))
        p.drawText(
            QRectF(x, it.y, it.x + it.width - x - 8, it.height),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            it.label,
        )


# Lucide-Dateiname je Knopf (assets/icons/).
ICON_DATEI = {
    "pen": "pencil",
    "undo": "undo-2",
    "redo": "redo-2",
    "clear": "eraser",
    "shoot": "camera",
    "cancel": "x",
}
ICON_SIZE = 17


def _paint_icon(p, name: str, cx: float, cy: float, farbe, qt) -> None:
    """Symbol mittig auf (cx, cy) malen — echte SVG-Datei, in der Knopf-Farbe."""
    datei = ICON_DATEI.get(name)
    if datei is None:
        return
    pix = load_icon(datei, farbe.name(), ICON_SIZE)
    if pix is None:
        return
    p.drawPixmap(int(cx - ICON_SIZE / 2), int(cy - ICON_SIZE / 2), pix)
