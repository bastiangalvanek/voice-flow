"""macOS-Berechtigungen aktiv anfragen statt still zu scheitern.

Problem: pynput prueft nur, OB der Prozess vertraut ist — es loest den
System-Dialog nie aus. Ergebnis: F8 bleibt stumm und der Nutzer sieht nie
eine Abfrage. Dieses Modul feuert die Abfragen explizit:

  Bedienungshilfen  AXIsProcessTrustedWithOptions(prompt=True)
                    -> Dialog + Eintrag in der Systemeinstellungs-Liste
  Mikrofon          AVCaptureDevice.requestAccessForMediaType("soun")
  Bildschirm (F6)   CGRequestScreenCaptureAccess()

Alles nur auf macOS; auf anderen Plattformen sind die Funktionen No-Ops.
"""

from __future__ import annotations

import logging
import subprocess
import sys

log = logging.getLogger(__name__)

_IS_MAC = sys.platform == "darwin"


def accessibility_ok(prompt: bool = True) -> bool:
    """True wenn Bedienungshilfen erteilt. prompt=True loest den Dialog aus."""
    if not _IS_MAC:
        return True
    try:
        from ApplicationServices import (
            AXIsProcessTrusted,
            AXIsProcessTrustedWithOptions,
            kAXTrustedCheckOptionPrompt,
        )

        if AXIsProcessTrusted():
            return True
        if prompt:
            AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
        return False
    except Exception as ex:
        log.warning("AX-Pruefung fehlgeschlagen (%s) — oeffne Einstellungen direkt.", ex)
        if prompt:
            open_accessibility_settings()
        return False


def request_microphone() -> None:
    """Mikrofon-Dialog anstossen (asynchron, blockiert nicht)."""
    if not _IS_MAC:
        return
    try:
        from AVFoundation import AVCaptureDevice

        AVCaptureDevice.requestAccessForMediaType_completionHandler_(
            "soun", lambda granted: log.info("Mikrofon-Freigabe: %s", granted)
        )
    except Exception as ex:
        log.debug("Mikrofon-Anfrage nicht moeglich: %s", ex)


def request_screen_capture() -> bool:
    """Bildschirmaufnahme (fuer F6/F7-Screenshots). True wenn schon erlaubt."""
    if not _IS_MAC:
        return True
    try:
        from Quartz import CGPreflightScreenCaptureAccess, CGRequestScreenCaptureAccess

        if CGPreflightScreenCaptureAccess():
            return True
        CGRequestScreenCaptureAccess()
        return False
    except Exception as ex:
        log.debug("Screen-Capture-Anfrage nicht moeglich: %s", ex)
        return False


def open_accessibility_settings() -> None:
    """Systemeinstellungen direkt auf der Bedienungshilfen-Seite oeffnen."""
    try:
        subprocess.Popen(
            ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"]
        )
    except Exception as ex:
        log.debug("Konnte Einstellungen nicht oeffnen: %s", ex)


def ensure_all(notify=None) -> bool:
    """Alle Rechte pruefen/anfragen. Gibt True zurueck wenn F8 funktionieren kann.

    notify: optionale Callback(str) fuer eine sichtbare Meldung in der UI.
    """
    if not _IS_MAC:
        return True
    request_microphone()
    request_screen_capture()
    ok = accessibility_ok(prompt=True)
    if not ok:
        msg = (
            "Bedienungshilfen fehlen — F8 kann nicht funktionieren. "
            "Systemeinstellungen > Datenschutz & Sicherheit > Bedienungshilfen: "
            "Voice Flow (bzw. python) aktivieren, dann App neu starten."
        )
        log.warning(msg)
        if notify:
            try:
                notify(msg)
            except Exception:
                pass
        open_accessibility_settings()
    return ok
