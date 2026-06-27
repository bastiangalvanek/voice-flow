"""Das premium Toast-QWidget (SaaS-Stil) + Icon-Glyphen.

Lazy PyQt6-Import in build_toast_class(), damit der Top-Level-Import nicht
scheitert wenn Qt fehlt (gleiches Muster wie overlay_qt._build_qt_class).
Design-Tokens identisch zur Pille -> Pille + Toasts wie aus einer Hand.
"""
from __future__ import annotations

import logging

from voice_flow.notifications import ToastSpec, style_for, truncate

log = logging.getLogger(__name__)

# Design-Tokens (Spiegel von overlay_qt.py)
SURFACE_RAISED = "#16161C"
SURFACE_BASE = "#0B0B0F"
TEXT_PRIMARY = "#F2F2F5"
TEXT_SECONDARY = "#9B9BA3"
TEXT_DIM = "#6A6A74"

CARD_WIDTH = 360
CARD_RADIUS = 15
PAD = 15
ICON_BADGE = 32
GAP_ICON_TEXT = 13
THUMB = 46
SHADOW_PAD = 26
ACTION_ROW_H = 30


def build_toast_class():
    from PyQt6.QtCore import (QEasingCurve, QPoint, QPropertyAnimation, QRectF,
                              Qt, QTimer, pyqtSignal)
    from PyQt6.QtGui import (QColor, QFont, QPainter, QPainterPath, QPen,
                             QPixmap, QPolygonF, QLinearGradient)
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QWidget

    def _rgb(hexc: str) -> QColor:
        return QColor(hexc)

    class ToastWidget(QWidget):
        sig_dismiss = pyqtSignal(object)

        def __init__(self, spec: ToastSpec, on_dismiss):
            super().__init__()
            self.spec = spec
            self._on_dismiss = on_dismiss
            self._accent = _rgb(style_for(spec.kind)["accent"])
            self._icon = style_for(spec.kind)["icon"]
            self._hovered = False
            self._closing = False

            self._thumb: QPixmap | None = None
            if spec.thumbnail_path:
                pix = QPixmap(spec.thumbnail_path)
                if not pix.isNull():
                    self._thumb = pix.scaled(
                        THUMB, THUMB,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )

            self._has_actions = bool(spec.actions)
            self._card_h = self._compute_card_height()

            flags = (
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
            )
            if not self._has_actions:
                # Reiner Info-Toast: click-through, null Stoerung.
                flags |= Qt.WindowType.WindowTransparentForInput
            self.setWindowFlags(flags)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.resize(CARD_WIDTH + SHADOW_PAD * 2, self._card_h + SHADOW_PAD * 2)

            self._fonts()

            # Action-Hotspots (Rechtecke in Widget-Koords) fuer Klick-Erkennung.
            self._action_rects: list[tuple[object, object]] = []

            self._dismiss_timer = QTimer(self)
            self._dismiss_timer.setSingleShot(True)
            self._dismiss_timer.timeout.connect(self.dismiss)

            self._anim: QPropertyAnimation | None = None

        # ---- Geometrie ----

        @property
        def desired_height(self) -> int:
            return self._card_h

        def _compute_card_height(self) -> int:
            h = 30 + (20 if self.spec.subtitle else 6)  # Titel (+Subtitle)
            h = max(h, ICON_BADGE + 4)
            if self._thumb is not None:
                h = max(h, THUMB + 4)
            base = h + PAD * 2 - 6
            if self._has_actions:
                base += ACTION_ROW_H
            return max(64, base)

        def _fonts(self):
            self._f_title = QFont("Segoe UI Variable Display", 11)
            if not self._f_title.exactMatch():
                self._f_title = QFont("Segoe UI", 11)
            self._f_title.setWeight(QFont.Weight.DemiBold)
            self._f_sub = QFont("Segoe UI Variable Text", 9)
            if not self._f_sub.exactMatch():
                self._f_sub = QFont("Segoe UI", 9)
            self._f_action = QFont("Segoe UI", 9)
            self._f_action.setWeight(QFont.Weight.DemiBold)

        # ---- Lifecycle ----

        def animate_in(self, target: QPoint):
            self.move(target.x(), target.y())
            self.show()
            self.setWindowOpacity(0.0)
            self._anim = QPropertyAnimation(self, b"windowOpacity")
            self._anim.setDuration(190)
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._anim.start()
            if self.spec.duration_ms > 0 and not self._hovered:
                self._dismiss_timer.start(self.spec.duration_ms)

        def move_to(self, target: QPoint):
            if self._closing:
                return
            self._anim = QPropertyAnimation(self, b"pos")
            self._anim.setDuration(180)
            self._anim.setStartValue(self.pos())
            self._anim.setEndValue(target)
            self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._anim.start()

        def dismiss(self):
            if self._closing:
                return
            self._closing = True
            self._dismiss_timer.stop()
            self._anim = QPropertyAnimation(self, b"windowOpacity")
            self._anim.setDuration(150)
            self._anim.setStartValue(self.windowOpacity())
            self._anim.setEndValue(0.0)
            self._anim.setEasingCurve(QEasingCurve.Type.InCubic)
            self._anim.finished.connect(self._finalize)
            self._anim.start()

        def _finalize(self):
            self.hide()
            self._on_dismiss(self)
            self.deleteLater()

        # ---- Maus ----

        def enterEvent(self, _e):
            self._hovered = True
            self._dismiss_timer.stop()

        def leaveEvent(self, _e):
            self._hovered = False
            if self.spec.duration_ms > 0 and not self._closing:
                self._dismiss_timer.start(1200)

        def mousePressEvent(self, e):
            pos = e.position()
            for rect, cb in self._action_rects:
                if rect.contains(pos):
                    try:
                        cb()
                    except Exception as ex:
                        log.warning("Toast-Action fehlgeschlagen: %s", ex)
                    self.dismiss()
                    return
            if self._close_rect().contains(pos):
                self.dismiss()

        # ---- Paint ----

        def _close_rect(self):
            return QRectF(self.width() - SHADOW_PAD - 26, SHADOW_PAD + 8, 18, 18)

        def paintEvent(self, _e):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

            x0, y0 = SHADOW_PAD, SHADOW_PAD
            w, h = CARD_WIDTH, self._card_h

            # Multi-Layer Shadow (dezent, wie Pille)
            for ext, oy, alpha in [(18, 7, 6), (11, 4, 12), (5, 2, 24), (2, 1, 34)]:
                pth = QPainterPath()
                pth.addRoundedRect(QRectF(x0 - ext, y0 + oy - ext, w + ext * 2, h + ext * 2),
                                   CARD_RADIUS + ext, CARD_RADIUS + ext)
                p.fillPath(pth, QColor(0, 0, 0, alpha))

            # Card body
            card = QRectF(x0, y0, w, h)
            grad = QLinearGradient(x0, y0, x0, y0 + h)
            grad.setColorAt(0.0, _rgb(SURFACE_RAISED))
            grad.setColorAt(1.0, _rgb(SURFACE_BASE))
            body = QPainterPath()
            body.addRoundedRect(card, CARD_RADIUS, CARD_RADIUS)
            p.fillPath(body, grad)
            p.setPen(QPen(QColor(255, 255, 255, 18), 1))
            p.drawPath(body)

            # Linke Accent-Kante (3px, premium status-cue)
            edge = QPainterPath()
            edge.addRoundedRect(QRectF(x0, y0 + 10, 3, h - 20), 1.5, 1.5)
            ac = QColor(self._accent)
            p.fillPath(edge, ac)

            # Icon-Badge
            bx = x0 + PAD
            by = y0 + PAD
            badge = QPainterPath()
            badge.addRoundedRect(QRectF(bx, by, ICON_BADGE, ICON_BADGE), 9, 9)
            bg = QColor(self._accent)
            bg.setAlpha(38)
            p.fillPath(badge, bg)
            self._paint_icon(p, bx, by, ICON_BADGE)

            # Text
            tx = bx + ICON_BADGE + GAP_ICON_TEXT
            text_right = x0 + w - PAD - (THUMB + 10 if self._thumb else 0)
            avail_chars = max(8, int((text_right - tx) / 7.0))

            p.setFont(self._f_title)
            p.setPen(_rgb(TEXT_PRIMARY))
            if self.spec.subtitle:
                ty = by + 14
            else:
                ty = by + ICON_BADGE / 2 + 5
            p.drawText(QPointF(tx, ty), truncate(self.spec.title, avail_chars))

            if self.spec.subtitle:
                p.setFont(self._f_sub)
                p.setPen(_rgb(TEXT_SECONDARY))
                p.drawText(QPointF(tx, ty + 17), truncate(self.spec.subtitle, avail_chars + 6))

            # Thumbnail
            if self._thumb is not None:
                thx = x0 + w - PAD - THUMB
                thy = y0 + (h - (ACTION_ROW_H if self._has_actions else 0)) / 2 - THUMB / 2
                clip = QPainterPath()
                clip.addRoundedRect(QRectF(thx, thy, THUMB, THUMB), 8, 8)
                p.save()
                p.setClipPath(clip)
                p.drawPixmap(int(thx), int(thy), self._thumb)
                p.restore()
                p.setPen(QPen(QColor(255, 255, 255, 22), 1))
                p.drawPath(clip)

            # Close x
            cr = self._close_rect()
            p.setPen(QPen(_rgb(TEXT_DIM), 1.4))
            p.drawLine(QPointF(cr.left() + 5, cr.top() + 5), QPointF(cr.right() - 5, cr.bottom() - 5))
            p.drawLine(QPointF(cr.right() - 5, cr.top() + 5), QPointF(cr.left() + 5, cr.bottom() - 5))

            # Action-Row
            self._action_rects = []
            if self._has_actions:
                p.setFont(self._f_action)
                ax = tx
                ay = y0 + h - ACTION_ROW_H + 6
                for label, cb in self.spec.actions:
                    p.setPen(QColor(self._accent))
                    tw = p.fontMetrics().horizontalAdvance(label)
                    rect = QRectF(ax - 8, ay - 4, tw + 16, 24)
                    chip = QPainterPath()
                    chip.addRoundedRect(rect, 7, 7)
                    fill = QColor(self._accent)
                    fill.setAlpha(28)
                    p.fillPath(chip, fill)
                    p.drawText(QPointF(ax, ay + 13), label)
                    self._action_rects.append((rect, cb))
                    ax += tw + 26

        def _paint_icon(self, p, bx, by, size):
            cx, cy = bx + size / 2, by + size / 2
            ac = QColor(self._accent)
            pen = QPen(ac, 1.8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            k = self._icon
            if k == "rec":
                p.setBrush(ac)
                p.drawEllipse(QPointF(cx, cy), 5, 5)
            elif k == "cam":
                p.drawRoundedRect(QRectF(cx - 8, cy - 5, 16, 11), 2.5, 2.5)
                p.drawLine(QPointF(cx - 4, cy - 5), QPointF(cx - 2, cy - 8))
                p.drawLine(QPointF(cx - 2, cy - 8), QPointF(cx + 2, cy - 8))
                p.drawLine(QPointF(cx + 2, cy - 8), QPointF(cx + 4, cy - 5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(cx, cy + 0.5), 3, 3)
            elif k == "text":
                for i, wln in enumerate((10, 8, 6)):
                    yy = cy - 5 + i * 5
                    p.drawLine(QPointF(cx - 5, yy), QPointF(cx - 5 + wln, yy))
            elif k == "paste":
                p.drawRoundedRect(QRectF(cx - 6, cy - 7, 12, 15), 2, 2)
                p.drawRoundedRect(QRectF(cx - 3, cy - 9, 6, 4), 1.2, 1.2)
            elif k == "check":
                p.drawPolyline(QPolygonF([QPointF(cx - 6, cy), QPointF(cx - 1.5, cy + 4.5), QPointF(cx + 6, cy - 5)]))
            elif k == "warn":
                p.drawPolygon(QPolygonF([QPointF(cx, cy - 7), QPointF(cx + 7, cy + 6), QPointF(cx - 7, cy + 6)]))
                p.drawLine(QPointF(cx, cy - 2), QPointF(cx, cy + 2))
                p.setBrush(ac)
                p.drawEllipse(QPointF(cx, cy + 4.2), 0.9, 0.9)
            else:  # info
                p.drawEllipse(QPointF(cx, cy), 7, 7)
                p.setBrush(ac)
                p.drawEllipse(QPointF(cx, cy - 3), 0.9, 0.9)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawLine(QPointF(cx, cy - 1), QPointF(cx, cy + 4))

    return ToastWidget


# Stack-Tuning
TOAST_MARGIN = 22
TOAST_GAP = 12
TOAST_MAX_VISIBLE = 5


def build_toast_manager_class():
    """ToastManager lebt im Qt-Thread der RecordingOverlay (eine QApplication).

    Cross-Thread-Notify via sig_notify (thread-safe). Stack top-right auf dem
    Monitor unter dem Cursor, neuester oben, variable Hoehen, Max-Cap.
    """
    from PyQt6.QtCore import QObject, QPoint, Qt, pyqtSignal
    from PyQt6.QtGui import QCursor, QGuiApplication

    from voice_flow.notifications import stack_positions

    Toast = build_toast_class()

    class ToastManager(QObject):
        sig_notify = pyqtSignal(object)  # ToastSpec

        def __init__(self):
            super().__init__()
            self._stack: list = []  # neuester zuerst (Index 0 = oben)
            self.sig_notify.connect(self._on_notify, Qt.ConnectionType.QueuedConnection)

        def _screen_rect(self):
            scr = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
            g = scr.availableGeometry()
            return (g.x(), g.y(), g.width(), g.height())

        def _on_notify(self, spec):
            w = Toast(spec, self._on_dismiss)
            self._stack.insert(0, w)
            while len(self._stack) > TOAST_MAX_VISIBLE:
                self._stack.pop().dismiss()
            self._place(animate_new=w)

        def _full_height(self, w) -> int:
            return w.desired_height + SHADOW_PAD * 2

        def _place(self, animate_new=None):
            heights = [self._full_height(w) for w in self._stack]
            # SHADOW_PAD kompensieren: das Karten-Pixel sitzt SHADOW_PAD innerhalb des Fensters.
            positions = stack_positions(
                heights, self._screen_rect(),
                margin=TOAST_MARGIN - SHADOW_PAD, gap=TOAST_GAP,
                width=CARD_WIDTH + SHADOW_PAD * 2,
            )
            for w, (x, y) in zip(self._stack, positions):
                target = QPoint(x, y)
                if w is animate_new:
                    w.animate_in(target)
                else:
                    w.move_to(target)

        def _on_dismiss(self, w):
            if w in self._stack:
                self._stack.remove(w)
            self._place()

        def clear(self):
            for w in list(self._stack):
                w.dismiss()
            self._stack.clear()

    return ToastManager
