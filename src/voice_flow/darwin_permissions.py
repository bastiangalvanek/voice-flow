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
from pathlib import Path

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


def screen_capture_ok() -> bool:
    """Darf die App den Bildschirm mitlesen? (Nur pruefen, kein Dialog.)

    18.08 Bastian: "es macht Screenshots vom Desktop, nicht von dem, was ich
    gerade sehe". Ohne diese Freigabe liefert macOS nur den Hintergrund und die
    eigenen Fenster - ohne Fehler, ohne Hinweis. Deshalb wird vor jedem
    Screenshot geprueft.
    """
    if not _IS_MAC:
        return True
    try:
        from Quartz import CGPreflightScreenCaptureAccess

        return bool(CGPreflightScreenCaptureAccess())
    except Exception as ex:
        log.debug("Bildschirm-Freigabe nicht pruefbar: %s", ex)
        return True


def open_screen_capture_settings() -> None:
    """Systemeinstellungen auf der Seite Bildschirmaufnahme oeffnen."""
    if not _IS_MAC:
        return
    import subprocess

    subprocess.run(
        ["open",
         "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"],
        check=False)


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
    # KEIN CGRequestScreenCaptureAccess beim Start: das ist der Dialog "moechte
    # den Bildschirm aufnehmen", und er kam bei jedem Start erneut. Gefragt wird
    # erst beim ersten Screenshot (siehe app._bildschirm_freigabe_ok).
    heile_alte_bildschirm_freigabe()
    # Zustand NACH der Bereinigung genau einmal ablesen und melden.
    if not screen_capture_ok():
        log.info("Bildschirmaufnahme noch nicht erlaubt — es wird beim ersten "
                 "Screenshot danach gefragt, nicht jetzt.")
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
        # KEIN open_accessibility_settings() mehr: der System-Dialog von
        # accessibility_ok(prompt=True) reicht, und der Status steht dauerhaft
        # im Voice-Flow-Fenster. Zwei aufspringende Fenster beim Start waren der
        # Grund fuer "andauernd muckt das System" (Bastian, 19.08.).
    return ok


# ── Status + Reparatur ───────────────────────────────────────────────
# 19.08 Bastian: "einen Button, wo ich sehe: ist es da, ja oder nein".
# Statt Dialoge zu feuern, wird der Zustand ANGEZEIGT und nur auf Knopfdruck
# repariert.

def microphone_ok() -> bool:
    """Mikrofon erteilt? Nur pruefen, kein Dialog."""
    if not _IS_MAC:
        return True
    try:
        from AVFoundation import AVCaptureDevice

        # 3 = AVAuthorizationStatusAuthorized
        return int(AVCaptureDevice.authorizationStatusForMediaType_("soun")) == 3
    except Exception as ex:
        log.debug("Mikrofon-Status nicht pruefbar: %s", ex)
        return True


def permission_status() -> dict[str, bool]:
    """Alle drei Freigaben auf einen Blick — fuer die Anzeige im Fenster."""
    if not _IS_MAC:
        return {"microphone": True, "accessibility": True, "screen": True}
    return {
        "microphone": microphone_ok(),
        # prompt=False: reines Ablesen, sonst springt beim Aufklappen ein Dialog auf.
        "accessibility": accessibility_ok(prompt=False),
        "screen": screen_capture_ok(),
    }


BUNDLE_ID = "de.galvanek.voiceflow"


def repair_screen_capture(bundle_id: str = BUNDLE_ID) -> bool:
    """Verwaisten Bildschirm-Eintrag loeschen, damit macOS neu fragen kann.

    Der Grund (gemessen 19.08.): In der Liste "Aufnahme von Bildschirm &
    Systemaudio" stand "Voice Flow" mit AKTIVEM Schalter — die App bekam
    trotzdem nichts. Der Eintrag gehoerte zu einer aelteren Programmfassung.
    Ein sichtbarer Haken ist also kein Beweis fuer eine gueltige Freigabe.

    'tccutil reset' loescht den toten Eintrag; danach fragt macOS beim naechsten
    Screenshot wieder frisch. Braucht kein Administrator-Passwort.
    """
    if not _IS_MAC:
        return True
    try:
        r = subprocess.run(["tccutil", "reset", "ScreenCapture", bundle_id],
                           capture_output=True, text=True, timeout=15)
        log.info("tccutil reset ScreenCapture: rc=%s %s", r.returncode,
                 (r.stdout or r.stderr).strip())
        return r.returncode == 0
    except Exception as ex:
        log.warning("tccutil nicht ausfuehrbar: %s", ex)
        return False


# Einmalige Selbstheilung: tote Freigabe aus der Zeit vor dem Signatur-Fix.
_MARKER = Path.home() / ".voice-flow" / "state" / "screen_grant_cleaned"


def heile_alte_bildschirm_freigabe() -> bool:
    """Loescht EINMAL pro Rechner einen wirkungslosen Bildschirm-Eintrag.

    Vorgeschichte (19.08.): In den Systemeinstellungen stand "Voice Flow" mit
    aktivem Schalter, die App bekam trotzdem kein Bild. Der Eintrag war vor dem
    Signatur-Fix vom 18.08. erteilt worden und damit an die damalige Pruefsumme
    gebunden — jeder Neubau machte ihn ungueltig, ohne dass der Haken verschwand.
    Ein sichtbarer Haken ist deshalb kein Beweis fuer eine gueltige Freigabe.

    Seit dem Fix ist die Identitaet fest (designated => identifier). Eine ab
    jetzt erteilte Freigabe ueberlebt Updates — so wie es die Bedienungshilfen
    seither nachweislich tun. Nur der Altbestand muss einmal weg.

    Absicherung gegen Selbstschaden: Es wird ausschliesslich aufgeraeumt, wenn
    die Freigabe ohnehin nicht wirkt (Preflight False). Eine funktionierende
    Freigabe kann dieser Weg nicht loeschen. Danach nie wieder (Merker).
    """
    if not _IS_MAC:
        return False
    if _MARKER.exists():
        return False
    if screen_capture_ok():
        # Freigabe wirkt — nichts anzufassen, aber als erledigt vermerken.
        _marker_setzen()
        return False
    log.info("Einmalige Bereinigung: wirkungslose Bildschirm-Freigabe wird "
             "geloescht, damit macOS neu fragen kann.")
    ok = repair_screen_capture()
    _marker_setzen()
    return ok


def _marker_setzen() -> None:
    try:
        _MARKER.parent.mkdir(parents=True, exist_ok=True)
        _MARKER.write_text("erledigt\n")
    except Exception as ex:
        log.debug("Merker nicht schreibbar: %s", ex)
