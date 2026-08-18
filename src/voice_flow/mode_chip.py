"""Klickbarer Modus-Chip direkt an der Aufnahme-Pille.

18.08 Bastian: "beim Aufnahme-Button den Modus switchen auf Claude Code oder
AI-Web". Die Pille selbst kann das nicht — sie ist absichtlich
WindowTransparentForInput (Klicks gehen durch, sonst wuerde sie die App
blockieren, in die man gerade diktiert). Also ein eigenes, winziges Fenster
direkt daneben, das Klicks annimmt.

Der Chip ist genau dann da, wenn die Pille da ist — also nach F5. Es gab kurz
eine Hover-Anzeige im Ruhezustand; die ist am 18.08. wieder raus, weil sie beim
Arbeiten dauernd aufploppte ("der Scheiss ist einfach immer da").

Klick = anderer Modus (Claude Code <-> AI-Web). Der Chip zeigt das Zeichen des
Ziels: Clawd, das Claude-Code-Maskottchen, bzw. das runde Chrome-Zeichen.
geometry_beside() ist reine Mathematik und unit-getestet.
"""
from __future__ import annotations

import logging
import time

from voice_flow.target_mode import icon_path
from voice_flow.target_mode import label as mode_label

log = logging.getLogger(__name__)

# Optik wie die Aufnahme-Pille: gleiche Hoehe, gleicher Radius, gleiche Farben
# (Bastian 18.08: "einfach die gleiche Farbe wie bei der Standard-Voice-Flow-Pille").
CHIP_HEIGHT = 34
CHIP_RADIUS = 17
CHIP_PADDING_X = 12
CHIP_GAP = 8              # Abstand zur Pille
CHIP_ICON_HEIGHT = 22
CHIP_ICON_GAP = 8
CHIP_MIN_WIDTH = 92
CLICK_DEBOUNCE_SEC = 0.4  # doppelt zugestellte Klicks zusammenfassen


def geometry_beside(pill_rect: tuple[int, int, int, int], chip_width: int,
                    chip_height: int = CHIP_HEIGHT, gap: int = CHIP_GAP,
                    screen_left: int = 0) -> tuple[int, int]:
    """Position (x, y) des Chips links neben der sichtbaren Pille.

    pill_rect: (x, y, w, h) der SICHTBAREN Pille (ohne Schatten-Rand).
    Kein Platz links (Bildschirmrand) -> Chip rechts neben die Pille.
    """
    px, py, pw, ph = pill_rect
    y = py + (ph - chip_height) // 2
    x = px - gap - chip_width
    if x < screen_left + 4:
        x = px + pw + gap
    return (x, y)


def build_mode_chip_class():
    from PyQt6.QtCore import QRectF, Qt, QTimer, pyqtSignal, pyqtSlot
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import (QColor, QFont, QFontMetrics, QPainter,
                             QPainterPath, QPen, QPixmap)
    from PyQt6.QtWidgets import QWidget

    from voice_flow.theme import SURFACE_BASE, SURFACE_BORDER, TEXT_SECONDARY

    class ModeChipWidget(QWidget):
        sig_set_mode = pyqtSignal(str)          # Modus ("claude_code" | "ai_web")
        sig_place = pyqtSignal(object)          # pill_rect oder None (= verstecken)

        def __init__(self, on_click=None):
            super().__init__()
            self._on_click = on_click
            self._label = ""
            self._mode = ""
            self._icon: QPixmap | None = None
            self._pill_rect: tuple | None = None
            self._last_click = 0.0

            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            # Ohne das versteckt macOS Tool-Fenster, sobald eine fremde App aktiv
            # ist — und beim Diktieren ist IMMER eine fremde App aktiv.
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
            self.setCursor(Qt.CursorShape.PointingHandCursor)

            self._font = QFont("Segoe UI", 10)
            self._font.setWeight(QFont.Weight.DemiBold)
            self._metrics = QFontMetrics(self._font)

            self.sig_set_mode.connect(self._apply_mode)
            self.sig_place.connect(self._apply_place)

            self.hide()

        # ── Zustand ──────────────────────────────────────────────────
        @pyqtSlot(str)
        def _apply_mode(self, mode: str) -> None:
            self._mode = mode
            self._label = mode_label(mode)
            self._icon = self._load_icon(mode)
            icon_breite = self._icon.width() if self._icon else 0
            width = max(CHIP_MIN_WIDTH,
                        CHIP_PADDING_X * 2 + icon_breite + CHIP_ICON_GAP
                        + self._metrics.horizontalAdvance(self._label))
            self.resize(width, CHIP_HEIGHT)
            if self._pill_rect:
                self._move_beside(self._pill_rect)
            self.update()

        @pyqtSlot(object)
        def _apply_place(self, pill_rect) -> None:
            """Pille zeigt sich (rect) oder verschwindet (None)."""
            if pill_rect is None:
                self.hide()
                return
            self._pill_rect = tuple(pill_rect)
            self._move_beside(self._pill_rect)
            self.show()
            self.raise_()

        def _load_icon(self, mode: str):
            """Modus-Icon laden und auf Chip-Hoehe bringen (harte Pixelkanten)."""
            pfad = icon_path(mode)
            if pfad is None:
                return None
            pix = QPixmap(str(pfad))
            if pix.isNull():
                log.warning("Modus-Icon %s nicht ladbar.", pfad)
                return None
            return pix.scaledToHeight(CHIP_ICON_HEIGHT,
                                      Qt.TransformationMode.SmoothTransformation)

        def _move_beside(self, pill_rect) -> None:
            from PyQt6.QtWidgets import QApplication

            screen = QApplication.primaryScreen().availableGeometry()
            x, y = geometry_beside(pill_rect, self.width(), CHIP_HEIGHT,
                                   screen_left=screen.x())
            self.move(x, y)

        # ── Klick ────────────────────────────────────────────────────
        # Kein AppKit-Kunstgriff: Qt.Tool + WA_ShowWithoutActivating stellt den
        # Klick auch dann zu, wenn eine fremde App aktiv ist. Verworfen wurde
        # NSWindowStyleMaskNonactivatingPanel — damit fiel der Klick DURCH den
        # Chip in die App darunter (gemessen 18.08.).
        def mousePressEvent(self, event) -> None:
            if event.button() != Qt.MouseButton.LeftButton or self._on_click is None:
                return
            # Entprellung: macOS stellt EINEN Klick auf ein Fenster einer
            # inaktiven App manchmal zweimal zu (gemessen 18.08.: aus 5 Klicks
            # wurden 6 Schaltvorgaenge, einer sprang zwei Stufen weiter).
            # Schneller als CLICK_DEBOUNCE_SEC kann niemand bewusst umschalten.
            now = time.monotonic()
            if now - self._last_click < CLICK_DEBOUNCE_SEC:
                log.debug("Chip-Klick verworfen (Entprellung).")
                event.accept()
                return
            self._last_click = now
            try:
                if self._on_click is not None:
                    self._on_click()
            except Exception as ex:
                log.warning("Chip-Klick-Handler-Fehler: %s", ex)
            event.accept()

        # ── Malen ────────────────────────────────────────────────────
        def paintEvent(self, _event) -> None:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
            path = QPainterPath()
            path.addRoundedRect(rect, CHIP_RADIUS, CHIP_RADIUS)
            painter.fillPath(path, QColor(SURFACE_BASE))
            painter.strokePath(path, QColor(SURFACE_BORDER))

            x = CHIP_PADDING_X
            if self._icon is not None:
                painter.drawPixmap(x, (self.height() - self._icon.height()) // 2, self._icon)
                x += self._icon.width() + CHIP_ICON_GAP

            painter.setFont(self._font)
            painter.setPen(QColor(TEXT_SECONDARY))
            painter.drawText(
                QRectF(x, 0, self.width() - x - CHIP_PADDING_X, self.height()),
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                self._label,
            )

            painter.end()

    return ModeChipWidget


PEN_BUTTON_SIZE = 34
PEN_BUTTON_GAP = 8


def build_pen_button_class():
    """Runder Stift-Knopf RECHTS neben der Aufnahme-Pille.

    18.08 Bastian: "dieser Stift sollte eigentlich hier sein" — also nicht mehr
    am Modus-Chip links, sondern direkt rechts am Aufnahme-Knopf. Ein Klick
    oeffnet die Zeichen-Leiste.
    """
    from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal, pyqtSlot
    from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
    from PyQt6.QtWidgets import QWidget

    from voice_flow.theme import SURFACE_BASE, SURFACE_BORDER, TEXT_SECONDARY

    class PenButtonWidget(QWidget):
        sig_place = pyqtSignal(object)      # pill_rect oder None (= verstecken)

        def __init__(self, on_click=None):
            super().__init__()
            self._on_click = on_click
            self._last_click = 0.0
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.resize(PEN_BUTTON_SIZE, PEN_BUTTON_SIZE)
            self.sig_place.connect(self._apply_place)
            self.hide()

        @pyqtSlot(object)
        def _apply_place(self, pill_rect) -> None:
            if pill_rect is None:
                self.hide()
                return
            px, py, pw, ph = pill_rect
            self.move(px + pw + PEN_BUTTON_GAP, py + (ph - PEN_BUTTON_SIZE) // 2)
            self.show()
            self.raise_()

        def mousePressEvent(self, event) -> None:
            if event.button() != Qt.MouseButton.LeftButton or self._on_click is None:
                return
            now = time.monotonic()
            if now - self._last_click < CLICK_DEBOUNCE_SEC:
                event.accept()
                return
            self._last_click = now
            try:
                self._on_click()
            except Exception as ex:
                log.warning("Stift-Knopf-Handler-Fehler: %s", ex)
            event.accept()

        def paintEvent(self, _event) -> None:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
            kreis = QPainterPath()
            kreis.addEllipse(rect)
            p.fillPath(kreis, QColor(SURFACE_BASE))
            p.strokePath(kreis, QColor(SURFACE_BORDER))

            stift = QPen(QColor(TEXT_SECONDARY), 1.8)
            stift.setCapStyle(Qt.PenCapStyle.RoundCap)
            stift.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(stift)
            cx, cy = self.width() / 2, self.height() / 2
            p.drawLine(QPointF(cx - 6, cy + 6), QPointF(cx + 4, cy - 4))
            p.drawLine(QPointF(cx + 4, cy - 4), QPointF(cx + 6, cy - 2))
            p.drawLine(QPointF(cx + 6, cy - 2), QPointF(cx - 4, cy + 8))
            p.drawLine(QPointF(cx - 4, cy + 8), QPointF(cx - 7, cy + 8))
            p.end()

    return PenButtonWidget
