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

# Farben aus Lovables Leiste abgelesen.
BAR_BG = (22, 22, 27, 242)
BAR_BORDER = (255, 255, 255, 20)
ACTIVE_RING = (124, 106, 255)      # lila wie Lovables aktiver Annotation-Knopf
ACTIVE_TEXT = (240, 240, 245)
IDLE_TEXT = (205, 205, 214)
DISABLED_TEXT = (255, 255, 255, 70)
HOVER_FILL = (255, 255, 255, 22)


def paint_toolbar(p, items: list[ToolbarItem], active_tool: str,
                  qt, hat_striche: bool = True, hover_value=None) -> None:
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
        an = is_enabled(it, hat_striche)
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


def _paint_icon(p, name: str, cx: float, cy: float, farbe, qt) -> None:
    QRectF, QPointF, QColor, QPen = qt.QRectF, qt.QPointF, qt.QColor, qt.QPen
    if name == "pen":
        p.drawLine(QPointF(cx - 6, cy + 6), QPointF(cx + 4, cy - 4))
        p.drawLine(QPointF(cx + 4, cy - 4), QPointF(cx + 6, cy - 2))
        p.drawLine(QPointF(cx + 6, cy - 2), QPointF(cx - 4, cy + 8))
        p.drawLine(QPointF(cx - 4, cy + 8), QPointF(cx - 7, cy + 8))
    elif name == "undo":
        p.drawArc(QRectF(cx - 7, cy - 7, 14, 14), 40 * 16, 250 * 16)
        p.drawLine(QPointF(cx - 7, cy - 3), QPointF(cx - 7, cy - 8))
        p.drawLine(QPointF(cx - 7, cy - 8), QPointF(cx - 2, cy - 8))
    elif name == "redo":
        p.drawArc(QRectF(cx - 7, cy - 7, 14, 14), 290 * 16, 250 * 16)
        p.drawLine(QPointF(cx + 7, cy - 3), QPointF(cx + 7, cy - 8))
        p.drawLine(QPointF(cx + 7, cy - 8), QPointF(cx + 2, cy - 8))
    elif name == "shoot":
        # Kamera: Voice-Flow-eigen, nimmt den Bildschirm mit den Markierungen auf.
        p.drawRoundedRect(QRectF(cx - 8, cy - 5, 16, 12), 2.5, 2.5)
        p.drawLine(QPointF(cx - 3, cy - 5), QPointF(cx - 1.5, cy - 8))
        p.drawLine(QPointF(cx - 1.5, cy - 8), QPointF(cx + 2, cy - 8))
        p.drawEllipse(QPointF(cx, cy + 1), 3.2, 3.2)
    elif name == "cancel":
        p.drawLine(QPointF(cx - 5, cy - 5), QPointF(cx + 5, cy + 5))
        p.drawLine(QPointF(cx + 5, cy - 5), QPointF(cx - 5, cy + 5))
