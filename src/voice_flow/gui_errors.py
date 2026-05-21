"""GUI error display via native Win32 MessageBoxW (no Tk conflict).

Previously used tkinter.messagebox, which crashed with the Qt overlay ~30% of the
time (two Tk roots in different threads is unsupported).

Now: ctypes.windll.user32.MessageBoxW — Win32 API, thread-safe, no Tk dependency.
"""
from __future__ import annotations

import ctypes
import logging
import sys

log = logging.getLogger(__name__)

MB_OK = 0x00000000
MB_ICONERROR = 0x00000010
MB_ICONINFORMATION = 0x00000040
MB_SETFOREGROUND = 0x00010000
MB_TOPMOST = 0x00040000


def _show(title: str, message: str, icon_flag: int) -> None:
    if sys.platform != "win32":
        log.error("[%s] %s", title, message)
        return
    try:
        ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
            0,
            message,
            title,
            icon_flag | MB_OK | MB_SETFOREGROUND | MB_TOPMOST,
        )
    except Exception as ex:
        log.warning("MessageBoxW failed: %s", ex)


def show_error(title: str, message: str) -> None:
    _show(title, message, MB_ICONERROR)


def show_info(title: str, message: str) -> None:
    _show(title, message, MB_ICONINFORMATION)
