"""Qt-Rendering der vertikalen Loom-Toolbar (Pille + Button-Glyphen).

Getrennt von annotate.py, damit die Zeichen-Overlay-Datei klein bleibt und die
Icon-Render-Verantwortung bei der Toolbar liegt. Reine Mal-Logik, keine State-
Aenderung. Die konkreten Qt-Klassen kommen per Bundle rein (Factory-Pattern wie
im restlichen Projekt), damit kein Top-Level-Qt-Import noetig ist.
"""
from __future__ import annotations

from voice_flow.annotate_toolbar import PALETTE, ToolbarItem, pill_rect


def paint_toolbar(p, items: list[ToolbarItem], active_tool: str,
                  active_color_idx: int, qt) -> None:
    """Malt Pille + alle Buttons. `qt` = build_annotate_class-Qt-Bundle."""
    QColor, QPen, QPainterPath, QRectF = qt.QColor, qt.QPen, qt.QPainterPath, qt.QRectF
    left, top, w, h = pill_rect(items)
    pill = QPainterPath()
    pill.addRoundedRect(QRectF(left, top, w, h), w / 2, w / 2)
    p.fillPath(pill, QColor(20, 20, 26, 235))
    p.setPen(QPen(QColor(255, 255, 255, 22), 1))
    p.drawPath(pill)

    for it in items:
        active = (
            (it.kind == "tool" and it.value == active_tool)
            or (it.kind == "color" and it.value == active_color_idx)
        )
        _paint_button(p, it, active, qt)


def _paint_button(p, it: ToolbarItem, active: bool, qt) -> None:
    QColor, QPen, QBrush = qt.QColor, qt.QPen, qt.QBrush
    QRectF, QPainterPath, QPointF, Qt = qt.QRectF, qt.QPainterPath, qt.QPointF, qt.Qt
    cx, cy = it.x + it.size / 2, it.y + it.size / 2

    if active:
        hl = QPainterPath()
        hl.addRoundedRect(QRectF(it.x, it.y, it.size, it.size), 9, 9)
        p.fillPath(hl, QColor(255, 255, 255, 28))

    pen = QPen(QColor(235, 235, 240), 2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    if it.kind == "color":
        p.setBrush(QBrush(QColor(*PALETTE[int(it.value)])))
        ring = QColor(255, 255, 255, 235 if active else 90)
        p.setPen(QPen(ring, 2 if active else 1))
        p.drawEllipse(QPointF(cx, cy), 9, 9)
        return

    if it.kind == "tool":
        _paint_tool_glyph(p, str(it.value), cx, cy, QPointF, QRectF)
        return

    _paint_action_glyph(p, str(it.value), cx, cy, qt)


def _paint_tool_glyph(p, value: str, cx: float, cy: float, QPointF, QRectF) -> None:
    if value == "pen":
        p.drawLine(QPointF(cx - 8, cy + 8), QPointF(cx + 6, cy - 6))
        p.drawLine(QPointF(cx + 6, cy - 6), QPointF(cx + 9, cy - 3))
        p.drawLine(QPointF(cx + 9, cy - 3), QPointF(cx - 5, cy + 11))
    elif value == "arrow":
        p.drawLine(QPointF(cx - 8, cy + 8), QPointF(cx + 8, cy - 8))
        p.drawLine(QPointF(cx + 8, cy - 8), QPointF(cx + 2, cy - 8))
        p.drawLine(QPointF(cx + 8, cy - 8), QPointF(cx + 8, cy - 2))
    elif value == "rect":
        p.drawRect(QRectF(cx - 8, cy - 6, 16, 12))


def _paint_action_glyph(p, action: str, cx: float, cy: float, qt) -> None:
    QColor, QPen, QPainterPath = qt.QColor, qt.QPen, qt.QPainterPath
    QRectF, QPointF = qt.QRectF, qt.QPointF
    if action == "undo":
        p.drawArc(QRectF(cx - 8, cy - 8, 16, 16), 40 * 16, 250 * 16)
        p.drawLine(QPointF(cx - 8, cy - 4), QPointF(cx - 8, cy - 9))
        p.drawLine(QPointF(cx - 8, cy - 9), QPointF(cx - 3, cy - 9))
    elif action == "redo":
        # Gespiegelter Undo-Bogen: Pfeil zeigt nach rechts.
        p.drawArc(QRectF(cx - 8, cy - 8, 16, 16), 290 * 16, 250 * 16)
        p.drawLine(QPointF(cx + 8, cy - 4), QPointF(cx + 8, cy - 9))
        p.drawLine(QPointF(cx + 8, cy - 9), QPointF(cx + 3, cy - 9))
    elif action == "clear":
        # Muelltonne (klar von cancel-X unterscheidbar): Deckel + Korpus + Streben.
        p.drawLine(QPointF(cx - 8, cy - 6), QPointF(cx + 8, cy - 6))   # Deckel-Linie
        p.drawLine(QPointF(cx - 3, cy - 9), QPointF(cx + 3, cy - 9))   # Griff oben
        p.drawRect(QRectF(cx - 6, cy - 6, 12, 14))                     # Korpus
        p.drawLine(QPointF(cx - 2, cy - 2), QPointF(cx - 2, cy + 5))   # Strebe links
        p.drawLine(QPointF(cx + 2, cy - 2), QPointF(cx + 2, cy + 5))   # Strebe rechts
    elif action == "shoot":
        disc = QPainterPath()
        disc.addEllipse(QPointF(cx, cy), 13, 13)
        p.fillPath(disc, QColor(52, 211, 153))
        p.setPen(QPen(QColor(11, 11, 15), 2.2))
        p.drawRoundedRect(QRectF(cx - 6, cy - 4, 12, 9), 2, 2)
        p.drawEllipse(QPointF(cx, cy + 0.5), 2.6, 2.6)
    elif action == "cancel":
        p.setPen(QPen(QColor(255, 99, 97), 2.4))
        p.drawLine(QPointF(cx - 6, cy - 6), QPointF(cx + 6, cy + 6))
        p.drawLine(QPointF(cx + 6, cy - 6), QPointF(cx - 6, cy + 6))
