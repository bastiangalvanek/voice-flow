"""Klickbarer Modus-Chip direkt an der Aufnahme-Pille.

18.08 Bastian: "beim Aufnahme-Button den Modus switchen auf Claude Code oder
AI-Web". Die Pille selbst kann das nicht — sie ist absichtlich
WindowTransparentForInput (Klicks gehen durch, sonst wuerde sie die App
blockieren, in die man gerade diktiert). Also ein eigenes, winziges Fenster
direkt daneben, das Klicks annimmt.

Zwei Wege zum Chip:
  * waehrend Aufnahme/Verarbeitung ist er automatisch da (Pille ist ja auch da),
  * im Ruhezustand erscheint er, sobald die Maus in die Pillen-Zone unten in der
    Mitte fahrt (Hover-Poll per QCursor, kein System-Zugriff noetig).

Klick = naechste Einstellung (Auto -> Claude Code -> AI-Web -> Auto).
geometry_beside() ist reine Mathematik und unit-getestet.
"""
from __future__ import annotations

import logging

from voice_flow.target_mode import MODE_AI_WEB

log = logging.getLogger(__name__)

CHIP_HEIGHT = 26
CHIP_RADIUS = 13
CHIP_PADDING_X = 12
CHIP_GAP = 8            # Abstand zur Pille
CHIP_MIN_WIDTH = 96
HOVER_POLL_MS = 220
HOVER_MARGIN = 34       # wie weit um die Pille herum der Hover schon zaehlt

SURFACE = "#15151A"
BORDER = "#2E2E38"
TEXT = "#E6E6EA"
DOT_WEB = "#F07320"       # Galvanek-Orange = Bilder gehen raus
DOT_CLAUDE = "#6E8BFF"    # Blau = Pfade fuer Claude Code


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
    from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal, pyqtSlot
    from PyQt6.QtGui import QColor, QCursor, QFont, QFontMetrics, QPainter, QPainterPath
    from PyQt6.QtWidgets import QWidget

    class ModeChipWidget(QWidget):
        sig_set_mode = pyqtSignal(str, str)     # (label, effektiver Modus)
        sig_place = pyqtSignal(object)          # pill_rect oder None (= verstecken)

        def __init__(self, on_click=None):
            super().__init__()
            self._on_click = on_click
            self._label = ""
            self._mode = ""
            self._pill_rect: tuple | None = None
            self._pinned = False   # True = Pille ist sichtbar, Chip bleibt

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

            # Hover-Poll: im Ruhezustand den Chip zeigen, wenn die Maus in die
            # Pillen-Zone kommt. Billiger als ein globaler Maus-Hook und braucht
            # keine Bedienungshilfen-Freigabe.
            self._hover_timer = QTimer(self)
            self._hover_timer.setInterval(HOVER_POLL_MS)
            self._hover_timer.timeout.connect(self._poll_hover)
            self._hover_timer.start()
            self._idle_rect: tuple | None = None  # wo die Pille erscheinen WUERDE

            self.hide()

        # ── Zustand ──────────────────────────────────────────────────
        @pyqtSlot(str, str)
        def _apply_mode(self, label: str, mode: str) -> None:
            self._label = label
            self._mode = mode
            width = max(CHIP_MIN_WIDTH,
                        self._metrics.horizontalAdvance(label) + CHIP_PADDING_X * 2 + 14)
            self.resize(width, CHIP_HEIGHT)
            if self._pill_rect:
                self._move_beside(self._pill_rect)
            self.update()

        @pyqtSlot(object)
        def _apply_place(self, pill_rect) -> None:
            """Pille zeigt sich (rect) oder verschwindet (None)."""
            if pill_rect is None:
                self._pinned = False
                self.hide()
                return
            self._pill_rect = tuple(pill_rect)
            self._pinned = True
            self._move_beside(self._pill_rect)
            self.show()
            self.raise_()

        def set_idle_rect(self, rect) -> None:
            """Zone, in der die Pille erscheint — Basis fuer den Hover im Ruhezustand."""
            self._idle_rect = tuple(rect) if rect else None

        def _move_beside(self, pill_rect) -> None:
            from PyQt6.QtWidgets import QApplication

            screen = QApplication.primaryScreen().availableGeometry()
            x, y = geometry_beside(pill_rect, self.width(), CHIP_HEIGHT,
                                   screen_left=screen.x())
            self.move(x, y)

        # ── Hover im Ruhezustand ─────────────────────────────────────
        def _poll_hover(self) -> None:
            if self._pinned or self._idle_rect is None:
                return
            pos = QCursor.pos()
            if self._in_hover_zone(pos.x(), pos.y()):
                if not self.isVisible():
                    self._pill_rect = self._idle_rect
                    self._move_beside(self._idle_rect)
                    self.show()
                    self.raise_()
            elif self.isVisible():
                self.hide()

        def _in_hover_zone(self, x: int, y: int) -> bool:
            zx, zy, zw, zh = self._idle_rect
            in_pill_zone = (zx - HOVER_MARGIN <= x <= zx + zw + HOVER_MARGIN
                            and zy - HOVER_MARGIN <= y <= zy + zh + HOVER_MARGIN)
            if in_pill_zone:
                return True
            # Auf dem Chip selbst bleibt er stehen, sonst flackert er beim Zielen.
            g = self.geometry()
            return (g.x() <= x <= g.x() + g.width()
                    and g.y() <= y <= g.y() + g.height())

        # ── Klick ────────────────────────────────────────────────────
        # Kein AppKit-Kunstgriff noetig: Qt.Tool + WA_ShowWithoutActivating
        # stellt den Klick auch dann zu, wenn Chrome die aktive App ist
        # (gemessen 18.08.: 10 von 10 Klicks geschaltet, mit UND ohne
        # NSWindow-Praeparierung — der Stil NSWindowStyleMaskNonactivatingPanel
        # war sogar schaedlich, da fiel der Klick durch den Chip hindurch).
        def mousePressEvent(self, event) -> None:
            if event.button() != Qt.MouseButton.LeftButton or self._on_click is None:
                return
            try:
                self._on_click()
            except Exception as ex:
                log.warning("Modus-Chip-Klick-Handler-Fehler: %s", ex)
            event.accept()

        # ── Malen ────────────────────────────────────────────────────
        def paintEvent(self, _event) -> None:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
            path = QPainterPath()
            path.addRoundedRect(rect, CHIP_RADIUS, CHIP_RADIUS)
            painter.fillPath(path, QColor(SURFACE))
            painter.strokePath(path, QColor(BORDER))

            dot_color = QColor(DOT_WEB if self._mode == MODE_AI_WEB else DOT_CLAUDE)
            cy = self.height() / 2
            painter.setBrush(dot_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(CHIP_PADDING_X + 3, cy), 3.5, 3.5)

            painter.setFont(self._font)
            painter.setPen(QColor(TEXT))
            text_x = CHIP_PADDING_X + 14
            painter.drawText(
                QRectF(text_x, 0, self.width() - text_x - CHIP_PADDING_X, self.height()),
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                self._label,
            )
            painter.end()

    return ModeChipWidget
