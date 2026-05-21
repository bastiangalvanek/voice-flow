from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

log = logging.getLogger(__name__)

# Path to logo.png: voice-flow/logo.png (two levels above src/voice_flow/tray.py)
LOGO_PATH = Path(__file__).resolve().parents[2] / "logo.png"


class TrayIcon:
    """System tray icon with status color.

    If logo.png exists: load as alpha mask, tint with status color.
    Otherwise: drawn circle with white dot (fallback).
    """

    COLORS = {
        "idle": (140, 140, 140),       # grey
        "recording": (220, 50, 50),    # red
        "processing": (240, 140, 30),  # orange
        "error": (40, 40, 40),         # black
    }

    def __init__(self, on_quit: Callable[[], None]):
        import pystray

        self._pystray = pystray
        self._logo_cache: dict[str, Image.Image] = {}
        self._has_logo = LOGO_PATH.exists()
        if self._has_logo:
            log.debug("Tray uses logo.png from %s", LOGO_PATH)
        else:
            log.debug("Tray uses fallback icon (no logo.png at %s)", LOGO_PATH)

        self._icon = pystray.Icon(
            "voice-flow",
            self._icon_for("idle"),
            "Voice Flow — Idle",
            menu=pystray.Menu(
                pystray.MenuItem("Voice Flow", None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", lambda icon, item: on_quit()),
            ),
        )

    def _icon_for(self, state: str) -> Image.Image:
        if state in self._logo_cache:
            return self._logo_cache[state]

        color = self.COLORS.get(state, self.COLORS["idle"])

        if self._has_logo:
            img = self._tint_logo(color)
        else:
            img = self._draw_fallback(color)

        self._logo_cache[state] = img
        return img

    def _tint_logo(self, color: tuple[int, int, int]) -> Image.Image:
        """Load logo.png, replace all non-transparent pixels with color."""
        try:
            base = Image.open(LOGO_PATH).convert("RGBA")
        except Exception as ex:
            log.warning("Could not load logo.png: %s — using fallback.", ex)
            return self._draw_fallback(color)

        base.thumbnail((64, 64), Image.LANCZOS)
        alpha = base.getchannel("A")

        size = max(base.size)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        solid = Image.new("RGBA", base.size, color + (255,))
        canvas.paste(solid, ((size - base.size[0]) // 2, (size - base.size[1]) // 2), mask=alpha)
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
            log.debug("Tray update failed: %s", ex)

    def set_idle(self) -> None:
        self._set_state("idle", "Voice Flow — Idle")

    def set_recording(self) -> None:
        self._set_state("recording", "Voice Flow — Recording")

    def set_processing(self) -> None:
        self._set_state("processing", "Voice Flow — Processing")

    def set_error(self) -> None:
        self._set_state("error", "Voice Flow — Error")

    def run_detached(self) -> None:
        self._icon.run_detached()

    def stop(self) -> None:
        try:
            self._icon.stop()
        except Exception:
            pass
