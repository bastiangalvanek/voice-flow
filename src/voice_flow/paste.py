from __future__ import annotations

import logging
import time

import keyboard
import pyperclip

log = logging.getLogger(__name__)

# Critic P1-8: 80ms/150ms ist zu kurz fuer async-pasting Apps (Electron, Browser).
# 120/300 ist sicherer. Trade-off: minimal mehr Latenz, deutlich robuster.
PRE_PASTE_DELAY_SEC = 0.12
POST_PASTE_DELAY_SEC = 0.30


def paste_to_active_window(text: str, restore_clipboard: bool = False) -> None:
    """Setzt Text via Clipboard + Strg+V im aktiven Fenster ein.

    17.05 Bastian-Decision: restore_clipboard default jetzt FALSE.
    Begruendung: wenn Bastian beim F8-release NICHT in einem Textfeld ist
    (Desktop, Tray, falsches Fenster), schlaegt Ctrl+V fehl und sein
    Diktat-Text waere verloren weil clipboard zurueckgesetzt wurde.
    Jetzt: Text bleibt in Clipboard → er kann jederzeit mit Strg+V manuell
    einfuegen.

    WICHTIG: pyperclip kann nur Text lesen/schreiben. Wenn das Clipboard ein
    Bild oder File enthaelt, gibt paste() einen leeren String zurueck —
    Restore wuerde das Bild zerstoeren. Wir skippen Restore wenn old leer
    ist UND text non-leer war (Critic P1-9).
    """
    old: str | None = None
    if restore_clipboard:
        try:
            old = pyperclip.paste()
        except Exception as ex:
            log.warning("Konnte alten Clipboard-Inhalt nicht lesen: %s", ex)

    try:
        pyperclip.copy(text)
    except Exception as ex:
        log.error("Konnte Text nicht in Clipboard kopieren: %s", ex)
        raise

    time.sleep(PRE_PASTE_DELAY_SEC)
    keyboard.send("ctrl+v")
    time.sleep(POST_PASTE_DELAY_SEC)

    # Restore-Logik:
    # - Wenn restore_clipboard False → kein Restore, fertig.
    # - Wenn old None (Read fehlgeschlagen) → kein Restore, fertig.
    # - Wenn old leerer String UND text war non-leer → wahrscheinlich nicht-Text
    #   im Clipboard (Bild/File). Restore wuerde das ueberschreiben. Skip.
    if not restore_clipboard or old is None:
        return
    if old == "" and text != "":
        log.debug("Clipboard war non-text (Bild/File) — skip Restore um Bilddaten zu schuetzen.")
        return
    try:
        pyperclip.copy(old)
    except Exception as ex:
        log.warning("Konnte Clipboard nicht restaurieren: %s", ex)
