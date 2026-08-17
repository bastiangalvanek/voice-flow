"""Screenshot des Monitors unter dem Mauszeiger.

Reine Monitor-Auswahl (pick_monitor) ist getestet; das eigentliche Grabben
(grab_monitor_under_cursor) ist I/O (mss + Win-Cursor) und wird per
Headless-Grab-Smoke verifiziert, nicht im Unit-Test.
"""
from __future__ import annotations

import logging
import sys

from PIL import Image

if sys.platform == "win32":
    import ctypes
    import ctypes.wintypes

log = logging.getLogger(__name__)


def get_cursor_pos() -> tuple[int, int]:
    if sys.platform == "darwin":
        # pynput ist ohnehin Abhaengigkeit des Mac-Ports; Quartz-Koordinaten
        # passen direkt zu den mss-Monitor-Rechtecken.
        from pynput.mouse import Controller

        x, y = Controller().position
        return (int(x), int(y))
    pt = ctypes.wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)


def pick_monitor(cursor: tuple[int, int], monitors: list[dict]) -> dict:
    """Waehlt aus der mss-Monitorliste den unter dem Cursor.

    mss-Format: monitors[0] = virtueller All-Screen (ignorieren), ab [1] echte
    Monitore. Fallback wenn der Cursor in keinem echten Monitor liegt: erster
    echter Monitor.
    """
    cx, cy = cursor
    for mon in monitors[1:]:
        if (mon["left"] <= cx < mon["left"] + mon["width"]
                and mon["top"] <= cy < mon["top"] + mon["height"]):
            return mon
    return monitors[1] if len(monitors) > 1 else monitors[0]


def grab_monitor_under_cursor() -> Image.Image:
    # mss.mss() ist in mss 10.2 deprecated (raus in 11.0) -> direkt MSS() nutzen.
    from mss import MSS

    with MSS() as sct:
        mon = pick_monitor(get_cursor_pos(), sct.monitors)
        shot = sct.grab(mon)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
