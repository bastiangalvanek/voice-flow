"""Loom-Style Markier-/Zeichen-Overlay -> Screenshot MIT Zeichnung.

Zwei Schichten, bewusst getrennt:
  - Pure Logik (top-level, kein Qt): map_point + composite_strokes. Striche werden
    in LOGISCHEN Widget-Koords gesammelt und beim Shoot per Pillow ins (evtl.
    groessere) Pixel-Bild gemalt. Unit-getestet.
  - AnnotateOverlay (via build_annotate_class()-Factory): das transparente,
    maus-aktive Vollbild-QWidget mit der vertikalen Toolbar + Auto-Fade. Lazy
    Qt-Import wie overlay_qt._build_qt_class.

Thread-Regel: das Widget wird NIE aus dem keyboard-Hook-Thread erzeugt, sondern
ausschliesslich auf dem Qt-Thread via RecordingOverlay.open_annotate (Signal).
"""
from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable

from PIL import Image, ImageDraw

from voice_flow.shape_snap import snap
from voice_flow.annotate_toolbar import (  # noqa: F401
    is_enabled,
    STROKE_COLOR,
    ToolbarItem,
    build_toolbar,
    hit_test,
)
from voice_flow.annotate_toolbar_paint import paint_toolbar

log = logging.getLogger(__name__)

# 18.08 Bastian: "dann hat es jetzt einfach gecleart ohne Grund. Es darf aber
# erst clearen, wenn ich auf Clear druecke." Der frueher hier stehende
# Verblass-Timer (3,5 s) ist deshalb ersatzlos raus.


# ── Pure Logik (kein Qt) ────────────────────────────────────────────────


def map_point(widget_xy: tuple[float, float], mon_origin: tuple[int, int],
              scale: tuple[float, float]) -> tuple[int, int]:
    """Logische Widget-Koords -> Bild-Pixel. origin = Monitor-Ursprung im Bild.

    scale = (sx, sy): pro Achse, damit nicht-1:1-DPI (z.B. 150%) y nicht verzerrt.
    """
    x, y = widget_xy
    ox, oy = mon_origin
    sx, sy = scale
    return (int(round(x * sx)) + ox, int(round(y * sy)) + oy)


def _draw_arrow_head(draw: ImageDraw.ImageDraw, p0: tuple[int, int],
                     p1: tuple[int, int], color, width: int) -> None:
    """Spitze am Ende p1 der Linie p0->p1 (zwei kurze Schenkel)."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return
    ux, uy = dx / length, dy / length
    head = max(12, width * 4)        # Schenkellaenge skaliert mit Strichstaerke
    angle = math.radians(28)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    # Beide Schenkel = um +/- angle gegen die Richtung rotierter Einheitsvektor.
    for sign in (1, -1):
        rx = -ux * cos_a + sign * (-uy) * sin_a
        ry = -uy * cos_a - sign * (-ux) * sin_a
        end = (int(round(p1[0] + rx * head)), int(round(p1[1] + ry * head)))
        draw.line([p1, end], fill=color, width=width)


def composite_strokes(img: Image.Image, strokes: list,
                      scale: tuple[float, float],
                      origin: tuple[int, int]) -> Image.Image:
    """Malt die Vektor-Striche auf eine KOPIE des PNG. Groesse bleibt gleich.

    scale = (sx, sy): Punkte werden pro Achse gemappt; Linienbreite mit sx.
    """
    out = img.convert("RGB").copy()
    draw = ImageDraw.Draw(out)
    sx, _sy = scale
    for stroke in strokes:
        pts_widget = stroke.get("points") or []
        if not pts_widget:
            continue
        color = tuple(stroke.get("color", (240, 115, 32)))
        width = max(1, int(round(stroke.get("width", 4) * sx)))
        pts = [map_point(p, origin, scale) for p in pts_widget]
        kind = stroke.get("type", "pen")
        if kind == "pen":
            if len(pts) == 1:
                r = max(1, width // 2)
                x, y = pts[0]
                draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
            else:
                draw.line(pts, fill=color, width=width, joint="curve")
        elif kind == "arrow":
            p0, p1 = pts[0], pts[-1]
            draw.line([p0, p1], fill=color, width=width)
            _draw_arrow_head(draw, p0, p1, color, width)
        elif kind == "rect":
            (x0, y0), (x1, y1) = pts[0], pts[-1]
            box = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
            draw.rectangle(box, outline=color, width=width)
        elif kind == "ellipse":
            (x0, y0), (x1, y1) = pts[0], pts[-1]
            box = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
            draw.ellipse(box, outline=color, width=width)
        elif kind == "line":
            draw.line([pts[0], pts[-1]], fill=color, width=width)
    return out


# ── Qt-Widget (Factory, Lazy-Import) ────────────────────────────────────


def build_annotate_class():
    """Erzeugt die AnnotateOverlay-QWidget-Klasse zur Laufzeit (kein Top-Level-Qt)."""
    from types import SimpleNamespace

    from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
    from PyQt6.QtGui import (QBrush, QColor, QFont, QGuiApplication, QPainter,
                             QPainterPath, QPen, QPolygonF)
    from PyQt6.QtWidgets import QWidget

    # Qt-Klassen-Bundle fuer den ausgelagerten Toolbar-Renderer.
    _qt = SimpleNamespace(
        QColor=QColor, QPen=QPen, QBrush=QBrush, QRectF=QRectF,
        QPainterPath=QPainterPath, QPointF=QPointF, Qt=Qt, QFont=QFont,
    )

    def _screen_for(monitor: dict):
        """QScreen matchen auf den mss-Monitor (per logischem left/top)."""
        for scr in QGuiApplication.screens():
            g = scr.geometry()
            if g.x() == monitor.get("left") and g.y() == monitor.get("top"):
                return scr
        return QGuiApplication.primaryScreen()

    class AnnotateOverlay(QWidget):
        def __init__(self, monitor: dict, on_shoot: Callable[[Image.Image], None],
                     on_close: Callable[[], None] | None = None):
            super().__init__()
            self._monitor = monitor
            self._on_shoot = on_shoot
            self._on_close = on_close
            self._strokes: list[dict] = []
            # Zurueckgenommene Striche fuer "vor" (Lovable hat Undo UND Redo).
            self._redo_stack: list[dict] = []
            self._current: dict | None = None
            self._tool = "pen"
            self._fired = False  # genau ein on_shoot pro Overlay

            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            # 18.08 Bastian: "jedes Mal wenn ich auf Annotation druecke, oeffnet
            # sich wieder Voice Flow". Das Overlay darf die App nicht aktivieren,
            # sonst holt macOS das minimierte Hauptfenster mit hoch.
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            # macOS versteckt Tool-Fenster sobald die App inaktiv ist — F6 wird
            # aber IMMER aus einer fremden App heraus gedrueckt. Gleiche Kur wie
            # bei Pille und Toasts.
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
            self.setMouseTracking(True)
            self.setCursor(Qt.CursorShape.CrossCursor)

            scr = _screen_for(monitor)
            g = scr.geometry()  # logische Koords
            self.setGeometry(g.x(), g.y(), g.width(), g.height())
            # 18.08 Bastian: Leiste waagerecht unten mittig, direkt ueber der
            # Aufnahme-Pille, statt senkrecht am linken Rand.
            # Die Pille sitzt ueber dem Dock (nutzbarer Bereich), das Overlay
            # deckt aber den ganzen Bildschirm ab — Differenz durchreichen,
            # sonst laege die Leiste hinter dem Dock.
            from PyQt6.QtWidgets import QApplication as _QApp

            _nutzbar = _QApp.primaryScreen().availableGeometry()
            self._toolbar: list[ToolbarItem] = build_toolbar(
                g.width(), g.height(),
                nutzbar_unten=(_nutzbar.y() + _nutzbar.height()) - g.y())
            self._hover_value = None      # Knopf unter der Maus (fuer den Hover)


            self.show()
            self.raise_()
            # KEIN activateWindow(): das aktiviert die App Voice Flow, und macOS
            # holt dabei das Kontrollfenster wieder hervor.
            # 19.08 Bastian: "wenn ich es minimiere, soll es minimiert bleiben".
            # Die Leiste und das Zeichnen laufen ueber die Maus, die auch ohne
            # Aktivierung ankommt (beim Modus-Chip am 18.08. gemessen). ESC
            # kommt ueber den globalen Tastatur-Listener (siehe on_escape).

        # ---- State-Helfer ----

        def _color(self) -> tuple[int, int, int]:
            # Wie bei Lovable: eine Farbe, keine Auswahl.
            return STROKE_COLOR

        def _width(self) -> int:
            return 5

        # ---- Maus: zeichnen ODER Toolbar bedienen ----

        def mousePressEvent(self, e):
            pos = e.position()
            pt = (int(pos.x()), int(pos.y()))
            log.debug("Zeichen-Overlay: Klick bei %s", pt)
            hit = hit_test(pt, self._toolbar)
            if hit is not None:
                if is_enabled(hit, bool(self._strokes), bool(self._redo_stack)):
                    self._activate(hit)
                return
            self._current = {
                "type": self._tool, "color": self._color(),
                "width": self._width(), "points": [pt],
            }
            self.update()

        def mouseMoveEvent(self, e):
            # Hover in der Leiste nachfuehren (Lovable hellt den Knopf auf).
            pos_h = e.position()
            treffer = hit_test((int(pos_h.x()), int(pos_h.y())), self._toolbar)
            neuer_hover = treffer.value if treffer is not None else None
            if neuer_hover != self._hover_value:
                self._hover_value = neuer_hover
                self.update()
            if self._current is None:
                return
            pos = e.position()
            pt = (int(pos.x()), int(pos.y()))
            if self._current["type"] == "pen":
                self._current["points"].append(pt)
            else:
                # arrow/rect/ellipse: nur Start + aktuelles Ende
                self._current["points"] = [self._current["points"][0], pt]
            self.update()

        def mouseReleaseEvent(self, e):
            if self._current is not None and len(self._current["points"]) >= 1:
                # 18.08 Bastian (nach Lovable): "lass los und dann wird es so ein
                # Kreis. Oder ein Pfeil." Nur beim Freihand-Werkzeug — wer
                # bewusst Pfeil oder Rechteck gewaehlt hat, will keine Umdeutung.
                if self._current["type"] == "pen":
                    form, punkte = snap([(float(x), float(y))
                                         for x, y in self._current["points"]])
                    if form != "pen":
                        self._current["type"] = form
                        self._current["points"] = [(int(x), int(y)) for x, y in punkte]
                        log.debug("Form erkannt: %s", form)
                self._strokes.append(self._current)
                self._redo_stack.clear()   # neuer Strich = Vorwaerts-Weg endet
            self._current = None
            self.update()

        def _activate(self, item: ToolbarItem) -> None:
            if item.kind == "tool":
                # 18.08 Bastian: "bekomme nur mit Escape den Stift weg". Ein
                # Klick auf den schon aktiven Stift schaltet das Zeichnen wieder
                # aus — genau wie bei Lovable.
                if str(item.value) == self._tool:
                    self.close()
                    return
                self._tool = str(item.value)
            elif item.kind == "action":
                self._do_action(str(item.value))
            self.update()

        def _do_action(self, action: str) -> None:
            if action == "undo":
                if self._strokes:
                    self._redo_stack.append(self._strokes.pop())
            elif action == "redo":
                if self._redo_stack:
                    self._strokes.append(self._redo_stack.pop())
            elif action == "clear":
                self._redo_stack.extend(reversed(self._strokes))
                self._strokes.clear()
            elif action == "shoot":
                self._shoot()
            elif action == "cancel":
                self.close()

        # ---- Tastatur ----

        def keyPressEvent(self, e):
            key = e.key()
            # F6 NICHT hier: bei offenem Overlay wuerde der globale keyboard-Hook
            # parallel ein zweites Overlay reopenen. Nur Enter/Return schiessen.
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._shoot()
            elif key == Qt.Key.Key_Escape:
                self.close()
            elif key == Qt.Key.Key_Z and (e.modifiers() & Qt.KeyboardModifier.ControlModifier):
                # Mit Shift = vor (wie ueberall), ohne = zurueck.
                self._do_action("redo" if (e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                                else "undo")
                self.update()

        # ---- Shoot: grabben + Striche einbrennen ----

        def _shoot(self) -> None:
            if self._fired:
                return
            self._fired = True
            # Striche-Snapshot VOR dem Verstecken nehmen.
            strokes = list(self._strokes)
            if self._current is not None:
                strokes.append(self._current)
            w = max(1, self.width())
            h = max(1, self.height())
            try:
                from PyQt6.QtWidgets import QApplication

                # Overlay (Dimm-Layer + live Qt-Striche) raus, sonst landet es
                # mit im Grab -> doppelte Striche + abgedunkeltes Bild.
                self.hide()
                QApplication.processEvents()
                time.sleep(0.05)  # Compositor Zeit geben, das Fenster zu entfernen
                img = self._grab_monitor()
                scale = (img.width / w, img.height / h)  # Pixel / logische Punkte, pro Achse
                composed = composite_strokes(img, strokes, scale, (0, 0))
                self._on_shoot(composed)
            except Exception as ex:
                log.error("Annotate-Shoot fehlgeschlagen: %s", ex)
            self.close()

        def _grab_monitor(self) -> Image.Image:
            from mss import MSS
            with MSS() as sct:
                shot = sct.grab(self._monitor)
                return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

        # ---- Paint ----

        def paintEvent(self, _e):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            # Leichter Dimm-Layer, damit man die Zeichenflaeche spuert.
            p.fillRect(self.rect(), QColor(0, 0, 0, 26))
            self._paint_strokes(p)
            self._paint_toolbar(p)

        def _paint_strokes(self, p):
            drawing = list(self._strokes)
            if self._current is not None:
                drawing.append(self._current)
            for st in drawing:
                pts = st["points"]
                if not pts:
                    continue
                col = QColor(*st["color"])
                pen = QPen(col, st["width"])
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                kind = st["type"]
                if kind == "pen":
                    if len(pts) == 1:
                        p.drawPoint(QPointF(*pts[0]))
                    else:
                        p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in pts]))
                elif kind == "arrow":
                    self._paint_arrow(p, pts[0], pts[-1], col, st["width"])
                elif kind == "rect":
                    (x0, y0), (x1, y1) = pts[0], pts[-1]
                    p.drawRect(int(min(x0, x1)), int(min(y0, y1)),
                               int(abs(x1 - x0)), int(abs(y1 - y0)))
                elif kind == "ellipse":
                    (x0, y0), (x1, y1) = pts[0], pts[-1]
                    p.drawEllipse(int(min(x0, x1)), int(min(y0, y1)),
                                  int(abs(x1 - x0)), int(abs(y1 - y0)))
                elif kind == "line":
                    p.drawLine(QPointF(*pts[0]), QPointF(*pts[-1]))

        def _paint_arrow(self, p, p0, p1, col, width):
            p.drawLine(QPointF(*p0), QPointF(*p1))
            dx, dy = p1[0] - p0[0], p1[1] - p0[1]
            length = math.hypot(dx, dy)
            if length < 1e-6:
                return
            ux, uy = dx / length, dy / length
            head = max(12, width * 4)
            ca, sa = math.cos(math.radians(28)), math.sin(math.radians(28))
            for sign in (1, -1):
                rx = -ux * ca + sign * (-uy) * sa
                ry = -uy * ca - sign * (-ux) * sa
                p.drawLine(QPointF(*p1),
                           QPointF(p1[0] + rx * head, p1[1] + ry * head))

        def _paint_toolbar(self, p):
            paint_toolbar(p, self._toolbar, self._tool, _qt,
                          hat_striche=bool(self._strokes),
                          hover_value=self._hover_value,
                          hat_zurueckgenommenes=bool(self._redo_stack))

        def closeEvent(self, e):
            # Der Bridge melden dass dieses Overlay zu ist (F6-Toggle + saubere Referenz).
            if self._on_close is not None:
                try:
                    self._on_close()
                except Exception:
                    pass
            e.accept()

    return AnnotateOverlay
