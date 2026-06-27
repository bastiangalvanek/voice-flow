from __future__ import annotations

import logging
from typing import Callable

from PIL import Image, ImageDraw

from voice_flow.logo_loader import resolve_logo_path

log = logging.getLogger(__name__)

# 27.06 Bastian: Flocke-Bug. Robuste Aufloesung statt fixem (fehlendem) logo.png.
LOGO_PATH = resolve_logo_path()


class TrayIcon:
    """System-Tray-Icon mit Galvanek-Flocke + Status-Punkt.

    Wenn logo.png existiert: echte Flocke + farbiger Status-Punkt (idle=grau,
    recording=rot, processing=orange). Sonst: gemalter Kreis (Fallback).
    """

    COLORS = {
        "idle": (140, 140, 140),       # grau
        "recording": (220, 50, 50),    # rot
        "processing": (240, 140, 30),  # galvanek-orange
        "error": (40, 40, 40),         # schwarz
    }

    def __init__(self, on_quit: Callable[[], None]):
        import pystray

        self._pystray = pystray
        self._logo_cache: dict[str, Image.Image] = {}
        self._has_logo = LOGO_PATH is not None
        if self._has_logo:
            log.debug("Tray nutzt logo.png aus %s", LOGO_PATH)
        else:
            log.debug("Tray nutzt Fallback-Icon (kein logo.png in %s)", LOGO_PATH)

        self._icon = pystray.Icon(
            "voice-flow",
            self._icon_for("idle"),
            "Voice Flow · Idle",
            menu=pystray.Menu(
                pystray.MenuItem("Voice Flow", None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Voice Flow beenden", lambda icon, item: on_quit()),
            ),
        )

    def _icon_for(self, state: str) -> Image.Image:
        if state in self._logo_cache:
            return self._logo_cache[state]

        color = self.COLORS.get(state, self.COLORS["idle"])

        if self._has_logo:
            img = self._logo_with_badge(color)
        else:
            img = self._draw_fallback(color)

        self._logo_cache[state] = img
        return img

    def _logo_with_badge(self, color: tuple[int, int, int]) -> Image.Image:
        """Echte Flocke (Original-Farben erhalten) + kleiner Status-Punkt unten-rechts.

        27.06 Bastian: vorher wurde das ganze Logo flach in die Status-Farbe
        eingefaerbt (Flocke war nur einfarbige Silhouette). Jetzt bleibt die
        Flocke wie sie ist, der Status kommt als Badge dazu.
        """
        try:
            base = Image.open(LOGO_PATH).convert("RGBA")
        except Exception as ex:
            log.warning("Konnte logo.png nicht laden: %s · Fallback.", ex)
            return self._draw_fallback(color)

        base.thumbnail((64, 64), Image.LANCZOS)
        canvas = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        canvas.paste(
            base,
            ((64 - base.size[0]) // 2, (64 - base.size[1]) // 2),
            base,
        )

        # Status-Punkt unten-rechts, weisser Rand fuer Kontrast auf jeder Taskbar.
        draw = ImageDraw.Draw(canvas)
        r = 11
        x1, y1, x2, y2 = 64 - 2 * r - 2, 64 - 2 * r - 2, 62, 62
        draw.ellipse((x1, y1, x2, y2), fill=color + (255,))
        draw.ellipse((x1, y1, x2, y2), outline=(255, 255, 255, 235), width=2)
        return canvas

    def _draw_fallback(self, color: tuple[int, int, int]) -> Image.Image:
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((8, 8, 56, 56), fill=color)
        draw.ellipse((26, 22, 38, 34), fill=(255, 255, 255))
        return img

    def _set_state(self, state: str, title: str) -> None:
        try:
            self._icon.icon = self._icon_for(state)
            self._icon.title = title
        except Exception as ex:
            log.debug("Tray-Update fehlgeschlagen: %s", ex)

    def set_idle(self) -> None:
        self._set_state("idle", "Voice Flow · Idle")

    def set_recording(self) -> None:
        self._set_state("recording", "Voice Flow · Recording")

    def set_processing(self) -> None:
        self._set_state("processing", "Voice Flow · Processing")

    def set_error(self) -> None:
        self._set_state("error", "Voice Flow · Error")

    def run_detached(self) -> None:
        self._icon.run_detached()

    def stop(self) -> None:
        try:
            self._icon.stop()
        except Exception:
            pass
