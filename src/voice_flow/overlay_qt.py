"""Premium PyQt6 floating pill overlay — endgame edition.

Warum PyQt6 statt tkinter:
- Echtes Anti-Aliasing (QPainter.RenderHint.Antialiasing) → smooth rounded corners
- Echte Drop-Shadows (QGraphicsDropShadowEffect mit gaussian blur)
- Linear-/radial-Gradients als first-class
- QPropertyAnimation mit QEasingCurve → Apple-style spring + bezier
- Vector-based Drawing → keine Pixel-Artefakte
- Native performance, 60fps trivial

Design-Spec aus /frontend-design (v4.0):
- 50px tall pill, full radius (full pill), surface_base #0B0B0F
- Multi-layer shadow: ambient 18px blur + direct 8px blur
- Logo links (Galvanek Sonne+Schneeflocke, 26px) mit radial halo per state
- Smooth scrolling Wave-Line in der rechten Pillen-Haelfte
- Range-mapped waveform (18-73%), heavy smoothing
- Deutsch: "Aufnahme" / "Transkribiere" / "{N} Woerter"

Thread-safety: läuft in eigenem QApplication-Thread. Communication via
thread-safe Qt signals (pyqtSignal) — sicher Cross-Thread.
"""
from __future__ import annotations

import logging
import math
import random
import sys
import threading
from collections import deque
from typing import Callable, Optional

from voice_flow.logo_loader import resolve_logo_path

log = logging.getLogger(__name__)

# 27.06 Bastian: Flocke-Bug. Robuste Aufloesung statt fixem (fehlendem) logo.png.
LOGO_PATH = resolve_logo_path()


# ── Design Tokens (eine Quelle: theme.py, damit der Modus-Chip dieselben nutzt) ──
from voice_flow.theme import (  # noqa: E402  (Tokens, kein Qt-Import)
    ACCENT_OK,
    ACCENT_PROC,
    ACCENT_REC,
    GALVANEK_ORANGE,
    SURFACE_BASE,
    SURFACE_BORDER,
    SURFACE_RAISED,
    TEXT_DIM,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class _PillWidget:
    """Lazy-init wrapper — QWidget wird erst beim Start des Qt-Threads erzeugt."""

    # ── Ultra-Compact-Spec (17.05 v2: noch kleiner + Shadow dezenter) ──
    PILL_HEIGHT = 34
    PILL_RADIUS = 17
    PADDING_X = 14
    LOGO_SIZE = 18
    LOGO_MARGIN = 10
    BOTTOM_OFFSET = 24       # naeher zur Taskbar (war 70)

    # Shadows DEUTLICH dezenter (Bastian-Feedback: "nicht so extrem")
    SHADOW_BLUR = 16         # war 28
    SHADOW_OFFSET_Y = 2      # war 5
    SHADOW_COLOR_ALPHA = 65  # war 95

    HALO_RADIUS = 22

    WIDTH_INFO = 220
    WIDTH_RECORDING = 250
    WIDTH_PROCESSING = 200
    WIDTH_SUCCESS = 200

    # ── Wave-Spec (17.05 Fix: "immer animiert ist kacke") ──
    WAVE_SAMPLES = 48
    WAVE_AREA_WIDTH = 100
    WAVE_MAX_AMPLITUDE = 8
    WAVE_MIN_AMPLITUDE = 0       # bei silence: KEINE Linie sichtbar
    WAVE_LINE_WIDTH = 1.3
    # Threshold: unter dem wird gar nichts gerendert
    WAVE_SILENCE_THRESHOLD = 0.05
    # Range-Mapping korrigiert: NUR aktiv wenn level über threshold
    # ramp von threshold..1 → 0.1..0.85 (statt vorher 0.18..0.73 immer)
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
    """Erstellt die echte PyQt6-Widget-Klasse zur Laufzeit (verhindert Top-Level-Import bei Qt-Missing)."""

    class PillWidget(QWidget):
        # Thread-safe signals
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
            # Chip links und Stift-Knopf rechts (von RecordingOverlay gesetzt).
            self._chip = None
            self._pen_button = None

            # Logo laden
            self._logo_pixmap = None
            if LOGO_PATH is not None and LOGO_PATH.exists():
                pix = QPixmap(str(LOGO_PATH))
                if not pix.isNull():
                    self._logo_pixmap = pix.scaled(
                        _PillWidget.LOGO_SIZE, _PillWidget.LOGO_SIZE,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )

            # Window setup
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
                | Qt.WindowType.WindowTransparentForInput  # Click-through (will move below)
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            # macOS versteckt Tool-Fenster sobald die App inaktiv ist — beim
            # Diktieren ist IMMER eine andere App aktiv. Ohne dieses Attribut
            # bleiben Pille und Toasts fuer den Nutzer unsichtbar.
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)

            # Window size: pill_width + shadow padding
            self._pill_height = _PillWidget.PILL_HEIGHT
            self._shadow_padding = _PillWidget.SHADOW_BLUR + 8
            self.resize(
                self.WIDTH_RECORDING + self._shadow_padding * 2,
                self._pill_height + self._shadow_padding * 2,
            )

            # Drop shadow effect — echter gaussian blur via Qt
            self._shadow = QGraphicsDropShadowEffect(self)
            self._shadow.setBlurRadius(_PillWidget.SHADOW_BLUR)
            self._shadow.setOffset(0, _PillWidget.SHADOW_OFFSET_Y)
            self._shadow.setColor(QColor(0, 0, 0, _PillWidget.SHADOW_COLOR_ALPHA))
            # Note: setGraphicsEffect mit translucent background hat tricky interplay.
            # Wir simulieren Shadow direkt in paintEvent (zuverlaessiger).

            # Render timer (60 fps target)
            self._render_timer = QTimer(self)
            self._render_timer.timeout.connect(self._on_tick)
            self._render_timer.setInterval(_PillWidget.TICK_MS)

            # Connect signals (thread-safe)
            self.sig_show_recording.connect(self._do_show_recording)
            self.sig_show_processing.connect(self._do_show_processing)
            self.sig_show_info.connect(self._do_show_info)
            self.sig_show_success.connect(self._do_show_success)
            self.sig_hide.connect(self._do_hide)
            self.sig_close_request.connect(self.close)

            # Fonts
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

        # ── Property: Width für Animationen (later) ──────────────────

        @property
        def WIDTH_INFO(self): return _PillWidget.WIDTH_INFO
        @property
        def WIDTH_RECORDING(self): return _PillWidget.WIDTH_RECORDING
        @property
        def WIDTH_PROCESSING(self): return _PillWidget.WIDTH_PROCESSING
        @property
        def WIDTH_SUCCESS(self): return _PillWidget.WIDTH_SUCCESS

        # ── Position ──────────────────────────────────────────────────

        def _position_centered_bottom(self):
            screen = QApplication.primaryScreen().availableGeometry()
            x = screen.x() + (screen.width() - self.width()) // 2
            y = screen.y() + screen.height() - self.height() - _PillWidget.BOTTOM_OFFSET + self._shadow_padding
            self.move(x, y)

        # ── State Transitions ────────────────────────────────────────

        @pyqtSlot()
        def _do_show_recording(self):
            self._enter_state(
                self.STATE_RECORDING,
                width=self.WIDTH_RECORDING,
                accent=ACCENT_REC,
                primary="Aufnahme",
                secondary="F8 zum Senden",
            )

        @pyqtSlot()
        def _do_show_processing(self):
            self._enter_state(
                self.STATE_PROCESSING,
                width=self.WIDTH_PROCESSING,
                accent=ACCENT_PROC,
                primary="Transkribiere",
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
            self._notify_chip(None)

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
            # Reset wave history for clean entry
            self._wave_samples = deque(
                [0.0] * _PillWidget.WAVE_SAMPLES, maxlen=_PillWidget.WAVE_SAMPLES
            )

            # Resize Window mit shadow-padding
            total_w = width + self._shadow_padding * 2
            total_h = self._pill_height + self._shadow_padding * 2
            self.resize(total_w, total_h)

            self._position_centered_bottom()
            self.show()
            self.update()
            self._render_timer.start()
            self._notify_chip(self.visible_pill_rect())

        def visible_pill_rect(self) -> tuple:
            """Rechteck der SICHTBAREN Pille (Fenster minus Schatten-Rand)."""
            return (
                self.x() + self._shadow_padding,
                self.y() + self._shadow_padding,
                self._current_width,
                self._pill_height,
            )

        def _notify_chip(self, rect) -> None:
            if self._chip is not None:
                self._chip.sig_place.emit(rect)
            if self._pen_button is not None:
                self._pen_button.sig_place.emit(rect)

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

                # 17.05 Fix: bei silence (lvl < threshold) → 0.0, kein dauer-baseline
                if lvl < _PillWidget.WAVE_SILENCE_THRESHOLD:
                    effective = 0.0
                else:
                    # Ramp von threshold..1 mapping nach offset..max
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
                # Nur Sinus/Noise wenn smooth_level signifikant > 0
                if self._smooth_level > 0.02:
                    sine = math.sin(self._tick * _PillWidget.WAVE_SINE_FREQ) * 0.5 + 0.5
                    noise = (random.random() - 0.5) * _PillWidget.WAVE_NOISE_AMP
                    sample = self._smooth_level * (0.7 + 0.3 * sine) + self._smooth_level * noise
                else:
                    sample = 0.0
                self._wave_samples.append(max(0.0, min(1.0, sample)))
            elif self._state == self.STATE_PROCESSING:
                self._processing_phase = (self._tick * _PillWidget.TICK_MS) / 1200.0

        # ── Paint ────────────────────────────────────────────────────

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

            # Pill geometry (Window contains shadow padding)
            pad = self._shadow_padding
            w = self._current_width
            h = self._pill_height
            pill_x = pad
            pill_y = pad
            radius = _PillWidget.PILL_RADIUS

            # ── Multi-step shadow — DEZENT (17.05 v2 Bastian: "nicht so extrem") ──
            # War: 14/26/40/60 alphas. Jetzt: ca 50% reduziert.
            shadow_layers = [
                (16, 5, 6),    # ambient, sehr soft
                (10, 3, 12),
                (5, 2, 22),
                (2, 1, 32),    # direct, sharper but still subtle
            ]
            for ext, oy, alpha in shadow_layers:
                path = QPainterPath()
                rect = QRectF(
                    pill_x - ext, pill_y + oy - ext,
                    w + ext * 2, h + ext * 2,
                )
                path.addRoundedRect(rect, radius + ext, radius + ext)
                painter.fillPath(path, QColor(0, 0, 0, alpha))

            # ── 2) Glass pill body (subtle gradient) ──
            pill_rect = QRectF(pill_x, pill_y, w, h)
            grad = QLinearGradient(pill_x, pill_y, pill_x, pill_y + h)
            grad.setColorAt(0.0, QColor(SURFACE_RAISED))
            grad.setColorAt(0.5, QColor(SURFACE_BASE))
            grad.setColorAt(1.0, QColor(SURFACE_BASE))
            path = QPainterPath()
            path.addRoundedRect(pill_rect, radius, radius)
            painter.fillPath(path, QBrush(grad))

            # Subtle hairline border (top edge highlight)
            painter.setPen(QPen(QColor(255, 255, 255, 14), 1))
            painter.drawPath(path)

            # ── 3) Logo halo (radial gradient) ──
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

            # ── 4) Logo ──
            if self._logo_pixmap is not None:
                lx = int(cursor_x)
                ly = int(content_cy - _PillWidget.LOGO_SIZE / 2)
                painter.drawPixmap(lx, ly, self._logo_pixmap)
            cursor_x += _PillWidget.LOGO_SIZE + _PillWidget.LOGO_MARGIN

            # ── 5) Primary + Secondary Text ──
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

            # ── 6) Right-side state-specific elements ──
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
                hexc = GALVANEK_ORANGE
            return _hex_to_rgb(hexc)

        def _paint_waveform(self, painter, right_edge, cy):
            # 17.05 Fix: bei silence GAR NICHTS rendern (keine durchgehende Linie!)
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
            min_amp = _PillWidget.WAVE_MIN_AMPLITUDE  # 0 → keine baseline-Linie
            max_amp = _PillWidget.WAVE_MAX_AMPLITUDE
            for i, s in enumerate(self._wave_samples):
                px = wave_x + (i / (n - 1)) * wave_w
                amp = min_amp + s * (max_amp - min_amp)
                # Edge taper
                edge = 1.0
                if i < 4:
                    edge = i / 4.0
                elif i > n - 5:
                    edge = (n - 1 - i) / 4.0
                amp *= edge
                points_top.append((px, cy - amp))
                points_bot.append((px, cy + amp))

            # Fill polygon (subtle wave-body)
            fill_path = QPainterPath()
            fill_path.moveTo(*points_top[0])
            for x, y in points_top[1:]:
                fill_path.lineTo(x, y)
            for x, y in reversed(points_bot):
                fill_path.lineTo(x, y)
            fill_path.closeSubpath()
            painter.fillPath(fill_path, fill_color)

            # Outline lines (crisp top + bot)
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
                # Ease-in-out scale
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


# ── Public API ──────────────────────────────────────────────────────────


class RecordingOverlay:
    """Public interface — identical to old tkinter overlay.

    Internally: Qt app läuft in eigenem Thread mit eigener QApplication.
    Alle public methods enqueue Befehle via thread-safe signals.
    """

    def __init__(self, always_visible: bool = False):
        self._level_provider: Optional[Callable[[], float]] = None
        self._always_visible = always_visible
        self._widget = None
        self._toasts = None  # ToastManager (premium event-notifications)
        self._control = None  # ControlWindow (sichtbar in Taskleiste)
        self._device_controls = None  # (devices, selected, on_select), falls vor _control gesetzt
        self._annotate_bridge = None  # erzeugt das F6-Zeichen-Overlay auf dem Qt-Thread
        self._chip = None  # ModeChipWidget (Claude Code vs. AI-Web)
        self._pen_button = None  # runder Stift-Knopf rechts an der Pille
        self._mode_chip_state = None  # (label, mode), falls vor dem Chip gesetzt
        self._on_mode_click_cb: Optional[Callable[[], None]] = None
        self._on_annotate_click_cb: Optional[Callable[[], None]] = None
        self._on_quit_cb: Optional[Callable[[], None]] = None
        self._app = None
        self._ready = threading.Event()
        self._available = False

        if sys.platform == "darwin":
            # macOS/AppKit erlaubt GUI-Objekte NUR im Haupt-Thread. Qt hier im
            # Thread hochzuziehen bricht mit NSException ab. Also: Aufbau jetzt
            # synchron (wir sind im Haupt-Thread), Ereignisschleife spaeter per
            # exec_main_loop() aus cli.main().
            self._thread = None
            self._run_qt(run_loop=False)
        else:
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
        # Falls Widget bereits da — Provider übernehmen
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

    def notify(self, kind, title: str, subtitle: str = "", thumbnail_path: str | None = None,
               actions=None, duration_ms: int = 4000) -> None:
        """Premium Event-Toast top-right (eigenes System, stoert die Pille nicht)."""
        if self._toasts is not None:
            from voice_flow.notifications import ToastSpec
            self._toasts.sig_notify.emit(ToastSpec(
                kind=kind, title=title, subtitle=subtitle,
                thumbnail_path=thumbnail_path, actions=actions or [],
                duration_ms=duration_ms,
            ))

    def set_mode_chip(self, mode: str) -> None:
        """Modus-Chip auf einen Modus stellen (thread-safe). Vor Chip-Existenz: gemerkt."""
        self._mode_chip_state = mode
        if self._chip is not None:
            self._chip.sig_set_mode.emit(mode)

    def set_mode_click_handler(self, cb: Callable[[], None]) -> None:
        """Was ein Klick auf den Chip macht — vom App-Controller gesetzt."""
        self._on_mode_click_cb = cb

    def _fire_mode_click(self) -> None:
        if self._on_mode_click_cb:
            self._on_mode_click_cb()

    def set_annotate_click_handler(self, cb: Callable[[], None]) -> None:
        """Was der Stift am Chip macht — vom App-Controller gesetzt."""
        self._on_annotate_click_cb = cb

    def _fire_annotate_click(self) -> None:
        if self._on_annotate_click_cb:
            self._on_annotate_click_cb()

    def set_quit_handler(self, cb: Callable[[], None]) -> None:
        """Vom CLI gesetzt: was passiert wenn das Control-Fenster geschlossen wird."""
        self._on_quit_cb = cb

    def _fire_quit(self) -> None:
        if self._on_quit_cb:
            self._on_quit_cb()

    def set_app_state(self, state: str) -> None:
        """Status-Punkt im Control-Fenster aktualisieren (thread-safe via Signal)."""
        if self._control is not None:
            self._control.set_status(state)

    def show_control_window(self) -> None:
        """Fenster sichtbar machen — vom CLI NACH set_quit_handler gerufen (kein Race)."""
        if self._control is not None:
            self._control.sig_show.emit()

    def set_device_controls(self, devices, selected_name, on_select) -> None:
        """Mikrofon-Dropdown im Control-Fenster befuellen (thread-safe)."""
        self._device_controls = (devices, selected_name, on_select)
        if self._control is not None:
            self._control.set_devices(devices, selected_name, on_select)

    def close_annotate(self) -> bool:
        """ESC: offene Zeichen-Ebene schliessen. True wenn eine offen war."""
        bruecke = getattr(self, "_annotate_bridge", None)
        if bruecke is None or bruecke._overlay is None:
            return False
        bruecke.sig_close.emit()
        return True

    def open_annotate(self, monitor: dict, on_shoot: Callable) -> None:
        """F6: Zeichen-Overlay oeffnen. THREAD-SAFE aus dem Hook-Thread.

        Das QWidget DARF nur auf dem Qt-Thread entstehen (Qt-Regel). Wir emittieren
        daher ein Signal, dessen Slot (queued) auf dem Qt-Thread laeuft und dort
        AnnotateOverlay instanziiert (gleiches Muster wie ToastManager.sig_notify).
        """
        log.debug("F6: bridge=%s", "da" if self._annotate_bridge is not None else "FEHLT")
        if self._annotate_bridge is not None:
            self._annotate_bridge.sig_open.emit(monitor, on_shoot)

    def stop(self) -> None:
        if self._widget:
            self._widget.sig_close_request.emit()
        if self._app is not None:
            # app.quit() MUSS im Qt-Thread laufen. Direkt aus einem Fremd-Thread
            # (Main-Thread beim Shutdown) BLOCKIERT es -> der Prozess haengt hier
            # und wird zum Zombie (Singleton-Port bleibt belegt). Queued in den
            # Qt-Thread posten = non-blocking.
            try:
                from PyQt6.QtCore import QMetaObject, Qt

                QMetaObject.invokeMethod(
                    self._app, "quit", Qt.ConnectionType.QueuedConnection
                )
            except Exception as ex:
                log.debug("app.quit invoke error: %s", ex)

    def _run_qt(self, run_loop: bool = True) -> None:
        try:
            from PyQt6.QtCore import (Qt, QRect, QRectF, QPointF, QTimer,
                                       pyqtSignal, pyqtSlot)
            from PyQt6.QtGui import (QPainter, QColor, QFont, QIcon, QLinearGradient,
                                      QRadialGradient, QPen, QBrush,
                                      QPainterPath, QPixmap)
            from PyQt6.QtWidgets import (QApplication, QWidget,
                                          QGraphicsDropShadowEffect)
        except ImportError as ex:
            log.warning("PyQt6 nicht installiert (%s) — Overlay deaktiviert", ex)
            self._ready.set()
            return

        try:
            if sys.platform == "darwin":
                # Sonst steht "Python" in Menuleiste und Dock. Muss VOR der
                # QApplication-Erzeugung passieren; pyobjc ist als Abhaengigkeit
                # von pystray/mss ohnehin installiert.
                try:
                    from Foundation import NSBundle
                    _info = NSBundle.mainBundle().infoDictionary()
                    if _info is not None:
                        _info["CFBundleName"] = "Voice Flow"
                        _info["CFBundleDisplayName"] = "Voice Flow"
                except Exception as ex:
                    log.debug("App-Name-Umbenennung fehlgeschlagen: %s", ex)

            self._app = QApplication.instance()
            if self._app is None:
                self._app = QApplication(sys.argv if hasattr(sys, "argv") else [])
            self._app.setApplicationName("Voice Flow")
            self._app.setApplicationDisplayName("Voice Flow")
            # Lifecycle haengt an keyboard.wait()/quit_handler, NICHT an Fenstern.
            # Sonst wuerde das Verstecken der Pille die ganze App beenden.
            self._app.setQuitOnLastWindowClosed(False)
            # Flocke als App-weites Fenster-/Taskleisten-Icon (scharfe .ico).
            from voice_flow.logo_loader import resolve_icon_path
            _icon = resolve_icon_path() or LOGO_PATH
            if _icon is not None:
                self._app.setWindowIcon(QIcon(str(_icon)))

            PillWidget = _build_qt_class(
                QWidget, QApplication, Qt, QPainter, QColor, QFont, QRect, QRectF,
                QPointF, QLinearGradient, QRadialGradient, QPen, QBrush,
                QPainterPath, QPixmap, QGraphicsDropShadowEffect, QTimer,
                pyqtSignal, pyqtSlot,
            )
            self._widget = PillWidget(self._level_provider)

            # Modus-Chip (Claude Code vs. AI-Web) direkt neben der Pille.
            try:
                from voice_flow.mode_chip import build_mode_chip_class

                self._chip = build_mode_chip_class()(on_click=self._fire_mode_click)
                self._widget._chip = self._chip
                # Stift-Knopf rechts neben der Pille (oeffnet die Zeichen-Leiste).
                from voice_flow.mode_chip import build_pen_button_class

                self._pen_button = build_pen_button_class()(
                    on_click=self._fire_annotate_click)
                self._widget._pen_button = self._pen_button
                if self._mode_chip_state is not None:
                    self._chip.sig_set_mode.emit(self._mode_chip_state)
            except Exception as ex:
                log.warning("Modus-Chip-Init fehlgeschlagen: %s", ex)
                self._chip = None

            # Premium Toast-System im selben Qt-Thread (eine QApplication).
            try:
                from voice_flow.notifications_widget import build_toast_manager_class
                self._toasts = build_toast_manager_class()()
            except Exception as ex:
                log.warning("Toast-Manager-Init fehlgeschlagen: %s", ex)
                self._toasts = None

            # Sichtbares Haupt-Fenster mit Taskleisten-Button (Loom-Modell).
            # Erzeugen aber NOCH NICHT zeigen — show erst nach set_quit_handler
            # (sonst Race: Schliessen vor verdrahtetem Quit -> verwaiste App).
            try:
                from voice_flow.control_window import build_control_window_class
                ControlWindow = build_control_window_class()
                self._control = ControlWindow(on_quit=self._fire_quit)
                # Falls die Mikrofon-Liste schon vor dem Fenster gesetzt wurde.
                if self._device_controls is not None:
                    self._control.set_devices(*self._device_controls)
            except Exception as ex:
                log.warning("Control-Fenster-Init fehlgeschlagen: %s", ex)
                self._control = None

            # F6-Zeichen-Overlay: Bruecke die das QWidget auf DIESEM Thread erzeugt.
            try:
                self._annotate_bridge = _build_annotate_bridge_class()()
            except Exception as ex:
                log.warning("Annotate-Bridge-Init fehlgeschlagen: %s", ex)
                self._annotate_bridge = None

            if self._always_visible:
                # Mode-neutral: show_ready() liefert den korrekten Hinweis (toggle/hold).
                self._widget.sig_show_info.emit("Voice Flow bereit", 3500)

            self._available = True
            self._ready.set()
            if run_loop:
                self._app.exec()
        except Exception as ex:
            log.exception("Qt-Overlay crashed: %s", ex)
            self._ready.set()

    def exec_main_loop(self, quit_event=None, poll_ms: int = 120) -> None:
        """Qt-Ereignisschleife im Haupt-Thread laufen lassen (nur macOS).

        Auf Windows/Linux laeuft die Schleife im overlay-qt-Thread und diese
        Methode kehrt sofort zurueck — dort parkt cli.main() weiter auf dem
        quit_event.

        quit_event: threading.Event. Wird per QTimer gepollt, weil ein
        threading.Event die Qt-Schleife nicht von sich aus aufwecken kann.
        """
        if sys.platform != "darwin" or self._app is None:
            return
        if quit_event is not None:
            from PyQt6.QtCore import QTimer

            timer = QTimer()
            timer.setInterval(poll_ms)
            timer.timeout.connect(
                lambda: self._app.quit() if quit_event.is_set() else None
            )
            timer.start()
            self._quit_timer = timer  # Referenz halten, sonst raeumt der GC ihn ab
        self._app.exec()


def _build_annotate_bridge_class():
    """QObject-Bruecke: erzeugt das Annotate-Overlay thread-safe auf dem Qt-Thread.

    sig_open(monitor, on_shoot) wird aus dem keyboard-Hook-Thread emittiert; der
    queued Slot laeuft garantiert auf dem Qt-Thread und instanziiert dort erst das
    QWidget. Referenz wird gehalten (sonst GC), beim naechsten Oeffnen ersetzt.
    """
    from PyQt6.QtCore import QObject, Qt, pyqtSignal

    from voice_flow.annotate import build_annotate_class

    AnnotateOverlay = build_annotate_class()

    class AnnotateBridge(QObject):
        sig_open = pyqtSignal(object, object)  # (monitor: dict, on_shoot: Callable)
        sig_close = pyqtSignal()               # ESC vom globalen Tastatur-Listener

        def __init__(self):
            super().__init__()
            self._overlay = None
            self._last_open = 0.0
            self.sig_open.connect(self._on_open, Qt.ConnectionType.QueuedConnection)
            self.sig_close.connect(self._on_close, Qt.ConnectionType.QueuedConnection)

        def _on_close(self):
            """Zeichen-Ebene schliessen, ohne die App zu aktivieren.

            Seit 19.08. holt die Zeichen-Ebene den Tastatur-Fokus nicht mehr
            (sonst kam das minimierte Kontrollfenster mit hoch). ESC muss
            deshalb von aussen kommen — ueber den globalen Listener.
            """
            if self._overlay is None:
                return
            try:
                self._overlay.close()
            except Exception:
                self._overlay = None

        def _clear_overlay(self):
            self._overlay = None

        def _on_open(self, monitor, on_shoot):
            log.debug("F6: Qt-Slot _on_open erreicht")
            # 27.06 Bastian: F6 ist ein TOGGLE. Ist ein Overlay offen -> F6 schliesst
            # es (Abbrechen, kein Shoot) und oeffnet KEIN neues. Sonst -> oeffnen.
            # Debounce nur gegen Typematic-Doppelfeuer (~50ms); 0.12s laesst bewusstes
            # schnelles Auf-dann-Zu durch (Critic P1-B1: 0.4s blockte den Toggle).
            import time
            now = time.monotonic()
            if now - self._last_open < 0.12:
                return
            self._last_open = now
            if self._overlay is not None:
                try:
                    self._overlay.close()  # closeEvent -> _clear_overlay -> _overlay=None
                except Exception:
                    self._overlay = None
                return
            self._overlay = AnnotateOverlay(monitor, on_shoot, on_close=self._clear_overlay)

    return AnnotateBridge


# ── Helpers ────────────────────────────────────────────────────────────


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hc = hex_color.lstrip("#")
    return int(hc[0:2], 16), int(hc[2:4], 16), int(hc[4:6], 16)


def _split_text(text: str) -> tuple[str, str]:
    if " · " in text:
        a, b = text.split(" · ", 1)
        return a, b
    return text, ""
