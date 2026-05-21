from __future__ import annotations

import logging
import time

import keyboard
import pyperclip

log = logging.getLogger(__name__)

# 120/300 ms is robust against async-pasting apps (Electron, browsers).
# Lower values lose pastes in those targets.
PRE_PASTE_DELAY_SEC = 0.12
POST_PASTE_DELAY_SEC = 0.30


def paste_to_active_window(text: str, restore_clipboard: bool = False) -> None:
    """Insert text into the active window via clipboard + Ctrl+V.

    restore_clipboard default is False so dictated text stays in the clipboard
    if auto-paste landed in the wrong window — user can re-paste manually.

    pyperclip can only read/write text. If the clipboard holds an image or file,
    paste() returns an empty string — restoring would destroy the image data.
    We skip restore when old=="" and text!="".
    """
    old: str | None = None
    if restore_clipboard:
        try:
            old = pyperclip.paste()
        except Exception as ex:
            log.warning("Could not read previous clipboard content: %s", ex)

    try:
        pyperclip.copy(text)
    except Exception as ex:
        log.error("Could not copy text to clipboard: %s", ex)
        raise

    time.sleep(PRE_PASTE_DELAY_SEC)
    keyboard.send("ctrl+v")
    time.sleep(POST_PASTE_DELAY_SEC)

    if not restore_clipboard or old is None:
        return
    if old == "" and text != "":
        log.debug("Clipboard held non-text (image/file) — skipping restore.")
        return
    try:
        pyperclip.copy(old)
    except Exception as ex:
        log.warning("Could not restore clipboard: %s", ex)
