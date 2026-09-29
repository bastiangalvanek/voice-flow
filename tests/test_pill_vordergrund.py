"""Pille darf nicht hinter einem fremden Topmost-Fenster verschwinden.

30.09.2026: Die Claude-App lief "immer im Vordergrund". War die Pille noch vom
letzten Diktat sichtbar und Bastian klickte in Claude, rutschte Claude in der
Topmost-Schicht nach oben. Beim naechsten F8 holten sich Chip und Stift nach
vorne, die Pille nicht — sichtbar blieben nur Chip und Stift.
"""
import os
import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Win32-Fensterreihenfolge")


def _sichtbare_fenster_von_oben():
    import ctypes
    import ctypes.wintypes as W

    user32 = ctypes.windll.user32
    reihe = []

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            reihe.append(hwnd)
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, W.HWND, W.LPARAM)(cb), 0)
    return reihe


def _fremdes_topmost_fenster():
    import ctypes

    user32 = ctypes.windll.user32
    user32.CreateWindowExW.restype = ctypes.c_void_p
    WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x8, 0x80, 0x08000000
    WS_POPUP, WS_VISIBLE = 0x80000000, 0x10000000
    hwnd = user32.CreateWindowExW(
        WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE, "STATIC", "fremd",
        WS_POPUP | WS_VISIBLE, 0, 0, 10, 10, None, None, None, None)
    assert hwnd, "Test-Fenster nicht erzeugt"
    return hwnd


def test_pille_liegt_nach_f8_ueber_fremdem_topmost_fenster():
    # Eigener Prozess: conftest stellt Qt auf "offscreen", dort gibt es keine
    # echten Fenster und damit keine Reihenfolge.
    pytest.importorskip("PyQt6")
    env = dict(os.environ, QT_QPA_PLATFORM="windows")
    lauf = subprocess.run([sys.executable, __file__], env=env, capture_output=True,
                          text=True, timeout=60)
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr


def _pruefen():
    import ctypes

    from voice_flow.overlay_qt import RecordingOverlay

    user32 = ctypes.windll.user32
    SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
    ov = RecordingOverlay()
    assert ov.available
    fremd = _fremdes_topmost_fenster()
    try:
        ov.show_success("12 Worte", 5000)
        time.sleep(0.5)
        pille, chip = int(ov._widget.winId()), int(ov._chip.winId())
        # Nutzer klickt ins fremde Fenster: es rutscht in der Topmost-Schicht nach oben.
        user32.SetWindowPos(ctypes.c_void_p(fremd), None, 0, 0, 0, 0,
                            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
        time.sleep(0.3)
        reihe = _sichtbare_fenster_von_oben()
        assert reihe.index(fremd) < reihe.index(pille), "Aufbau: fremdes Fenster muss oben liegen"

        ov.show_recording()
        time.sleep(0.5)
        reihe = _sichtbare_fenster_von_oben()
        assert reihe.index(chip) < reihe.index(fremd)
        assert reihe.index(pille) < reihe.index(fremd), "Pille liegt hinter fremdem Fenster"
    finally:
        ov.hide()
        user32.DestroyWindow(ctypes.c_void_p(fremd))


if __name__ == "__main__":
    _pruefen()
    os._exit(0)  # Qt-Thread nicht abbauen lassen (Absturz beim Interpreter-Ende)
