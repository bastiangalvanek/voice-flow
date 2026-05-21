"""Premium PyQt6 floating pill overlay.

Why PyQt6 over tkinter:
- Real anti-aliasing (QPainter.RenderHint.Antialiasing) → smooth rounded corners
- Real drop shadows (QGraphicsDropShadowEffect with gaussian blur)
- Linear/radial gradients as first-class citizens
- QPropertyAnimation with QEasingCurve → Apple-style spring + bezier
- Vector-based drawing → no pixel artifacts
- Native performance, 60 fps trivial

Design spec:
- 34 px tall pill, full radius, surface_base #0B0B0F
- Multi-layer shadow: ambient 16 px + direct 8 px
- Logo (when logo.png exists) with radial halo per state
- Smooth scrolling waveform in the right pill half
- Range-mapped waveform, heavy smoothing

Thread safety: runs in its own QApplication thread. Communication via
thread-safe Qt signals (pyqtSignal) — safe cross-thread.
"""
from __future__ import annotations

import logging
import math
import random
import sys
import threading
from collections import deque
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger(__name__)

LOGO_PATH = Path(__file__).resolve().parents[2] / "logo.png"


# ── Design tokens ──────────────────────────────────────────────────────
SURFACE_BASE = "#0B0B0F"
SURFACE_RAISED = "#15151A"
SURFACE_BORDER = "#26262E"
TEXT_PRIMARY = "#F2F2F5"
TEXT_SECONDARY = "#9B9BA3"
TEXT_DIM = "#5C5C66"
ACCENT_REC = "#FF453A"
ACCENT_PROC = "#FFB340"
ACCENT_OK = "#34D399"
ACCENT_IDLE = "#F07320"


class _PillWidget:
    """Lazy-init wrapper — QWidget is constructed when the Qt thread starts."""

    PILL_HEIGHT = 34
    PILL_RADIUS = 17
    PADDING_X = 14
    LOGO_SIZE = 18
    LOGO_MARGIN = 10
    BOTTOM_OFFSET = 24

    SHADOW_BLUR = 16
    SHADOW_OFFSET_Y = 2
    SHADOW_COLOR_ALPHA = 65

    HALO_RADIUS = 22

    WIDTH_INFO = 220
    WIDTH_RECORDING = 250
    WIDTH_PROCESSING = 200
    WIDTH_SUCCESS = 200

    WAVE_SAMPLES = 48
    WAVE_AREA_WIDTH = 100
    WAVE_MAX_AMPLITUDE = 8
    WAVE_MIN_AMPLITUDE = 0       # at silence: no visible line
    WAVE_LINE_WIDTH = 1.3
    WAVE_SILENCE_THRESHOLD = 0.05
    WAVE_RANGE_FACTOR = 0.75
    WAVE_RANGE_OFFSET = 0.10
    WAVE_LEVEL_SMOOTH = 0.88
    WAVE_SINE_FREQ = 0.38
    WAVE_NOISE_AMP = 0.08

    TICK_MS = 16
    PULSE_CYCLE_MS = 1400
    AUTO_HIDE_INFO_MS = 2400
    SUCCESS_FLASH_MS = 1100


def _build_qt_class(QWidget, QApplication, Qt, QPainter, QColor, QFont, QRect, QRectF,
                    QPointF, QLinearGradient, QRadialGradient, QPen, QBrush, QPainterPath,
                    QPixmap, QGraphicsDropShadowEffect, QTimer, pyqtSignal, pyqtSlot):
    """Build the real PyQt6 widget class at runtime (avoids top-level import on Qt-missing)."""

    class PillWidget(QWidget):
        sig_show_recording = pyqtSignal()
        sig_show_processing = pyqtSignal()
        sig_show_info = pyqtSignal(str, int)
        sig_show_success = pyqtSignal(str, int)
        sig_hide = pyqtSignal()
        sig_close_request = pyqtSignal()

        STATE_HIDDEN = "hidden"
        STATE_INFO = "info"
        STATE_RECORDING = "recording"
        STATE_PROCESSING = "processing"
        STATE_SUCCESS = "success"

        def __init__(self, level_provider: Optional[Callable[[], float]]):
            super().__init__()
            self._level_provider = level_provider
            self._state = self.STATE_HIDDEN
            self._current_width = _PillWidget.WIDTH_INFO
            self._primary_text = ""
            self._secondary_text = ""
            self._accent_color = ACCENT_OK
            self._tick = 0
            self._smooth_level = 0.0
            self._wave_samples = deque(
                [0.0] * _PillWidget.WAVE_SAMPLES, maxlen=_PillWidget.WAVE_SAMPLES
            )
            self._processing_phase = 0.0
            self._hide_timer = QTimer(self)
            self._hide_timer.setSingleShot(True)
            self._hide_timer.timeout.connect(self._on_hide_timer)

            self._logo_pixmap = None
            if LOGO_PATH.exists():
                pix = QPixmap(str(LOGO_PATH))
                if not pix.isNull():
                    self._logo_pixmap = pix.scaled(
                        _PillWidget.LOGO_SIZE, _PillWidget.LOGO_SIZE,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )

            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
                | Qt.WindowType.WindowTransparentForInput
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

            self._pill_height = _PillWidget.PILL_HEIGHT
            self._shadow_padding = _PillWidget.SHADOW_BLUR + 8
            self.resize(
                self.WIDTH_RECORDING + self._shadow_padding * 2,
                self._pill_height + self._shadow_padding * 2,
            )

            # Drop-shadow effect — real gaussian blur. setGraphicsEffect with translucent
            # background has tricky interplay; we simulate shadow directly in paintEvent.
            self._shadow = QGraphicsDropShadowEffect(self)
            self._shadow.setBlurRadius(_PillWidget.SHADOW_BLUR)
            self._shadow.setOffset(0, _PillWidget.SHADOW_OFFSET_Y)
            self._shadow.setColor(QColor(0, 0, 0, _PillWidget.SHADOW_COLOR_ALPHA))

            self._render_timer = QTimer(self)
            self._render_timer.timeout.connect(self._on_tick)
            self._render_timer.setInterval(_PillWidget.TICK_MS)

            self.sig_show_recording.connect(self._do_show_recording)
            self.sig_show_processing.connect(self._do_show_processing)
            self.sig_show_info.connect(self._do_show_info)
            self.sig_show_success.connect(self._do_show_success)
            self.sig_hide.connect(self._do_hide)
            self.sig_close_request.connect(self.close)

            self._font_primary = QFont("Segoe UI Variable Display", 11)
            if not self._font_primary.exactMatch():
                self._font_primary = QFont("Segoe UI", 11)
            self._font_primary.setWeight(QFont.Weight.Medium)
            self._font_primary.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 99)

            self._font_secondary = QFont("Segoe UI Variable Display", 9)
            if not self._font_secondary.exactMatch():
                self._font_secondary = QFont("Segoe UI", 9)
            self._font_secondary.setWeight(QFont.Weight.Normal)

            self.hide()

        @property
        def WIDTH_INFO(self): return _PillWidget.WIDTH_INFO
        @property
        def WIDTH_RECORDING(self): return _PillWidget.WIDTH_RECORDING
        @property
        def WIDTH_PROCESSING(self): return _PillWidget.WIDTH_PROCESSING
        @property
        def WIDTH_SUCCESS(self): return _PillWidget.WIDTH_SUCCESS

        def _position_centered_bottom(self):
            screen = QApplication.primaryScreen().availableGeometry()
            x = screen.x() + (screen.width() - self.width()) // 2
            y = screen.y() + screen.height() - self.height() - _PillWidget.BOTTOM_OFFSET + self._shadow_padding
            self.move(x, y)

        @pyqtSlot()
        def _do_show_recording(self):
            self._enter_state(
                self.STATE_RECORDING,
                width=self.WIDTH_RECORDING,
                accent=ACCENT_REC,
                primary="Recording",
                secondary="release to send",
            )

        @pyqtSlot()
        def _do_show_processing(self):
            self._enter_state(
                self.STATE_PROCESSING,
                width=self.WIDTH_PROCESSING,
                accent=ACCENT_PROC,
                primary="Transcribing",
                secondary="",
            )

        @pyqtSlot(str, int)
        def _do_show_info(self, text: str, duration_ms: int):
            primary, secondary = _split_text(text)
            self._enter_state(
                self.STATE_INFO,
                width=self.WIDTH_INFO,
                accent=ACCENT_OK,
                primary=primary,
                secondary=secondary,
            )
            self._hide_timer.start(duration_ms)

        @pyqtSlot(str, int)
        def _do_show_success(self, text: str, duration_ms: int):
            primary, secondary = _split_text(text)
            self._enter_state(
                self.STATE_SUCCESS,
                width=self.WIDTH_SUCCESS,
                accent=ACCENT_OK,
                primary=primary,
                secondary=secondary,
            )
            self._hide_timer.start(duration_ms)

        @pyqtSlot()
        def _do_hide(self):
            self._hide_timer.stop()
            self._state = self.STATE_HIDDEN
            self._render_timer.stop()
            self.hide()

        def _enter_state(self, new_state: str, width: int, accent: str,
                         primary: str, secondary: str):
            self._hide_timer.stop()
            self._state = new_state
            self._current_width = width
            self._accent_color = accent
            self._primary_text = primary
            self._secondary_text = secondary
            self._tick = 0
            self._smooth_level = 0.0
            self._wave_samples = deque(
                [0.0] * _PillWidget.WAVE_SAMPLES, maxlen=_PillWidget.WAVE_SAMPLES
            )

            total_w = width + self._shadow_padding * 2
            total_h = self._pill_height + self._shadow_padding * 2
            self.resize(total_w, total_h)

            self._position_centered_bottom()
            self.show()
            self.update()
            self._render_timer.start()

        @pyqtSlot()
        def _on_hide_timer(self):
            self._do_hide()

        @pyqtSlot()
        def _on_tick(self):
            self._tick += 1
            if self._state in (self.STATE_RECORDING, self.STATE_PROCESSING):
                self._advance_animation()
            self.update()

        def _advance_animation(self):
            if self._state == self.STATE_RECORDING:
                lvl = 0.0
                if self._level_provider:
                    try:
                        lvl = float(self._level_provider())
                    except Exception:
                        lvl = 0.0

                # On silence (lvl < threshold) → 0.0, no permanent baseline.
                if lvl < _PillWidget.WAVE_SILENCE_THRESHOLD:
                    effective = 0.0
                else:
                    ramp = (lvl - _PillWidget.WAVE_SILENCE_THRESHOLD) / (
                        1.0 - _PillWidget.WAVE_SILENCE_THRESHOLD
                    )
                    effective = min(1.0,
                        _PillWidget.WAVE_RANGE_OFFSET
                        + ramp * _PillWidget.WAVE_RANGE_FACTOR
                    )

                self._smooth_level = (
                    self._smooth_level * _PillWidget.WAVE_LEVEL_SMOOTH
                    + effective * (1 - _PillWidget.WAVE_LEVEL_SMOOTH)
                )
                if self._smooth_level > 0.02:
                    sine = math.sin(self._tick * _PillWidget.WAVE_SINE_FREQ) * 0.5 + 0.5
                    noise = (random.random() - 0.5) * _PillWidget.WAVE_NOISE_AMP
                    sample = self._smooth_level * (0.7 + 0.3 * sine) + self._smooth_level * noise
                else:
                    sample = 0.0
                self._wave_samples.append(max(0.0, min(1.0, sample)))
            elif self._state == self.STATE_PROCESSING:
                self._processing_phase = (self._tick * _PillWidget.TICK_MS) / 1200.0

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

            pad = self._shadow_padding
            w = self._current_width
            h = self._pill_height
            pill_x = pad
            pill_y = pad
            radius = _PillWidget.PILL_RADIUS

            # Multi-step shadow — subtle, ambient + direct layers.
            shadow_layers = [
                (16, 5, 6),
                (10, 3, 12),
                (5, 2, 22),
                (2, 1, 32),
            ]
            for ext, oy, alpha in shadow_layers:
                path = QPainterPath()
                rect = QRectF(
                    pill_x - ext, pill_y + oy - ext,
                    w + ext * 2, h + ext * 2,
                )
                path.addRoundedRect(rect, radius + ext, radius + ext)
                painter.fillPath(path, QColor(0, 0, 0, alpha))

            pill_rect = QRectF(pill_x, pill_y, w, h)
            grad = QLinearGradient(pill_x, pill_y, pill_x, pill_y + h)
            grad.setColorAt(0.0, QColor(SURFACE_RAISED))
            grad.setColorAt(0.5, QColor(SURFACE_BASE))
            grad.setColorAt(1.0, QColor(SURFACE_BASE))
            path = QPainterPath()
            path.addRoundedRect(pill_rect, radius, radius)
            painter.fillPath(path, QBrush(grad))

            painter.setPen(QPen(QColor(255, 255, 255, 14), 1))
            painter.drawPath(path)

            cursor_x = pill_x + _PillWidget.PADDING_X
            content_cy = pill_y + h / 2
            halo_center = QPointF(cursor_x + _PillWidget.LOGO_SIZE / 2, content_cy)
            halo_color = self._halo_color()
            halo_grad = QRadialGradient(halo_center, _PillWidget.HALO_RADIUS)
            halo_grad.setColorAt(0.0, QColor(halo_color[0], halo_color[1], halo_color[2], 80))
            halo_grad.setColorAt(0.5, QColor(halo_color[0], halo_color[1], halo_color[2], 30))
            halo_grad.setColorAt(1.0, QColor(halo_color[0], halo_color[1], halo_color[2], 0))
            painter.fillPath(
                self._circle_path(halo_center.x(), halo_center.y(), _PillWidget.HALO_RADIUS),
                QBrush(halo_grad),
            )

            if self._logo_pixmap is not None:
                lx = int(cursor_x)
                ly = int(content_cy - _PillWidget.LOGO_SIZE / 2)
                painter.drawPixmap(lx, ly, self._logo_pixmap)
            cursor_x += _PillWidget.LOGO_SIZE + _PillWidget.LOGO_MARGIN

            painter.setPen(QColor(TEXT_PRIMARY))
            painter.setFont(self._font_primary)
            primary_w = painter.fontMetrics().horizontalAdvance(self._primary_text)
            text_y = content_cy + painter.fontMetrics().ascent() / 2 - 2
            painter.drawText(QPointF(cursor_x, text_y), self._primary_text)

            if self._secondary_text:
                cursor_x += primary_w + 10
                painter.setPen(QColor(TEXT_SECONDARY))
                painter.setFont(self._font_secondary)
                sec_text_y = content_cy + painter.fontMetrics().ascent() / 2 - 2
                painter.drawText(QPointF(cursor_x, sec_text_y), self._secondary_text)

            if self._state == self.STATE_RECORDING:
                self._paint_waveform(painter, pill_x + w, content_cy)
            elif self._state == self.STATE_PROCESSING:
                self._paint_processing_dots(painter, pill_x + w, content_cy)
            elif self._state in (self.STATE_INFO, self.STATE_SUCCESS):
                self._paint_status_dot(painter, pill_x + w, content_cy)

        def _circle_path(self, cx, cy, r):
            p = QPainterPath()
            p.addEllipse(QPointF(cx, cy), r, r)
            return p

        def _halo_color(self) -> tuple[int, int, int]:
            if self._state == self.STATE_RECORDING:
                hexc = ACCENT_REC
            elif self._state == self.STATE_PROCESSING:
                hexc = ACCENT_PROC
            elif self._state == self.STATE_SUCCESS:
                hexc = ACCENT_OK
            else:
                hexc = ACCENT_IDLE
            return _hex_to_rgb(hexc)

        def _paint_waveform(self, painter, right_edge, cy):
            # On silence: render NOTHING (avoid a permanent baseline line).
            max_sample = max(self._wave_samples) if self._wave_samples else 0
            if max_sample < 0.02:
                return

            wave_w = _PillWidget.WAVE_AREA_WIDTH
            wave_x = right_edge - _PillWidget.PADDING_X - wave_w
            n = len(self._wave_samples)
            if n < 2:
                return

            color = QColor(self._accent_color)
            fill_color = QColor(color)
            fill_color.setAlpha(50)

            points_top = []
            points_bot = []
            min_amp = _PillWidget.WAVE_MIN_AMPLITUDE
            max_amp = _PillWidget.WAVE_MAX_AMPLITUDE
            for i, s in enumerate(self._wave_samples):
                px = wave_x + (i / (n - 1)) * wave_w
                amp = min_amp + s * (max_amp - min_amp)
                edge = 1.0
                if i < 4:
                    edge = i / 4.0
                elif i > n - 5:
                    edge = (n - 1 - i) / 4.0
                amp *= edge
                points_top.append((px, cy - amp))
                points_bot.append((px, cy + amp))

            fill_path = QPainterPath()
            fill_path.moveTo(*points_top[0])
            for x, y in points_top[1:]:
                fill_path.lineTo(x, y)
            for x, y in reversed(points_bot):
                fill_path.lineTo(x, y)
            fill_path.closeSubpath()
            painter.fillPath(fill_path, fill_color)

            top_path = QPainterPath()
            top_path.moveTo(*points_top[0])
            for x, y in points_top[1:]:
                top_path.lineTo(x, y)
            bot_path = QPainterPath()
            bot_path.moveTo(*points_bot[0])
            for x, y in points_bot[1:]:
                bot_path.lineTo(x, y)

            pen = QPen(color, _PillWidget.WAVE_LINE_WIDTH)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(top_path)
            painter.drawPath(bot_path)

        def _paint_processing_dots(self, painter, right_edge, cy):
            color = QColor(self._accent_color)
            dot_size = 5
            gap = 7
            count = 3
            total = count * dot_size + (count - 1) * gap
            start_x = right_edge - _PillWidget.PADDING_X - total

            for i in range(count):
                phase = (self._processing_phase - i * 0.18) % 1.0
                scale = 0.5 + 0.5 * math.sin(phase * 2 * math.pi)
                alpha = int(120 + 135 * scale)
                size = dot_size * (0.6 + 0.4 * scale)
                c = QColor(color)
                c.setAlpha(alpha)
                dx = start_x + i * (dot_size + gap) + (dot_size - size) / 2
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(c))
                painter.drawEllipse(QPointF(dx + size / 2, cy), size / 2, size / 2)

        def _paint_status_dot(self, painter, right_edge, cy):
            color = QColor(self._accent_color)
            dot_size = 5
            dx = right_edge - _PillWidget.PADDING_X - dot_size
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawEllipse(QPointF(dx + dot_size / 2, cy), dot_size / 2, dot_size / 2)

    return PillWidget


class RecordingOverlay:
    """Public interface — identical to the old tkinter overlay.

    Internally: Qt app runs in its own thread with its own QApplication.
    All public methods enqueue commands via thread-safe signals.
    """

    def __init__(self, always_visible: bool = False):
        self._level_provider: Optional[Callable[[], float]] = None
        self._always_visible = always_visible
        self._widget = None
        self._app = None
        self._ready = threading.Event()
        self._available = False

        self._thread = threading.Thread(
            target=self._run_qt, daemon=True, name="overlay-qt"
        )
        self._thread.start()
        self._ready.wait(timeout=5.0)

    @property
    def available(self) -> bool:
        return self._available

    def set_level_provider(self, provider: Callable[[], float]) -> None:
        self._level_provider = provider
        if self._widget is not None:
            self._widget._level_provider = provider

    def show_recording(self) -> None:
        if self._widget:
            self._widget.sig_show_recording.emit()

    def show_processing(self) -> None:
        if self._widget:
            self._widget.sig_show_processing.emit()

    def show_info(self, text: str, duration_ms: int = None) -> None:
        if self._widget:
            self._widget.sig_show_info.emit(text, duration_ms or _PillWidget.AUTO_HIDE_INFO_MS)

    def show_success(self, text: str, duration_ms: int = None) -> None:
        if self._widget:
            self._widget.sig_show_success.emit(text, duration_ms or _PillWidget.SUCCESS_FLASH_MS)

    def hide(self) -> None:
        if self._widget:
            self._widget.sig_hide.emit()

    def stop(self) -> None:
        if self._widget:
            self._widget.sig_close_request.emit()
        if self._app is not None:
            self._app.quit()

    def _run_qt(self) -> None:
        try:
            from PyQt6.QtCore import (Qt, QRect, QRectF, QPointF, QTimer,
                                       pyqtSignal, pyqtSlot)
            from PyQt6.QtGui import (QPainter, QColor, QFont, QLinearGradient,
                                      QRadialGradient, QPen, QBrush,
                                      QPainterPath, QPixmap)
            from PyQt6.QtWidgets import (QApplication, QWidget,
                                          QGraphicsDropShadowEffect)
        except ImportError as ex:
            log.warning("PyQt6 not installed (%s) — overlay disabled", ex)
            self._ready.set()
            return

        try:
            self._app = QApplication.instance()
            if self._app is None:
                self._app = QApplication(sys.argv if hasattr(sys, "argv") else [])

            PillWidget = _build_qt_class(
                QWidget, QApplication, Qt, QPainter, QColor, QFont, QRect, QRectF,
                QPointF, QLinearGradient, QRadialGradient, QPen, QBrush,
                QPainterPath, QPixmap, QGraphicsDropShadowEffect, QTimer,
                pyqtSignal, pyqtSlot,
            )
            self._widget = PillWidget(self._level_provider)

            if self._always_visible:
                self._widget.sig_show_info.emit("Voice Flow ready · hold F8", 3500)

            self._available = True
            self._ready.set()
            self._app.exec()
        except Exception as ex:
            log.exception("Qt overlay crashed: %s", ex)
            self._ready.set()


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hc = hex_color.lstrip("#")
    return int(hc[0:2], 16), int(hc[2:4], 16), int(hc[4:6], 16)


def _split_text(text: str) -> tuple[str, str]:
    if " · " in text:
        a, b = text.split(" · ", 1)
        return a, b
    return text, ""
