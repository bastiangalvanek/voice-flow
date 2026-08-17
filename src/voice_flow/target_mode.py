"""Ziel-Modus: bekommt der Empfaenger Datei-PFADE oder echte BILDER?

Hintergrund (18.08 Bastian): Claude Code liest die Screenshots selbst von der
Platte — ein Marker mit absolutem Pfad ist dort das Beste, was man einfuegen
kann. Ein Web-Chat (Lovable, ChatGPT, claude.ai, Gemini) hat das Verzeichnis
NICHT: dort ist der Pfad wertlos, dort muessen die Bilder als Dateien in die
Zwischenablage und per zweitem Cmd+V hinterher.

Zwei Modi, umgeschaltet wird per Klick am Chip neben der Pille. Eine automatische
Erkennung gab es kurz, ist auf Bastians Ansage vom 18.08 wieder raus
("den web auto mode raus, will selbst klicken, by default claude code").
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

MODE_CLAUDE_CODE = "claude_code"
MODE_AI_WEB = "ai_web"

DEFAULT_MODE = MODE_CLAUDE_CODE
MODE_CYCLE = (MODE_CLAUDE_CODE, MODE_AI_WEB)

LABELS = {
    MODE_CLAUDE_CODE: "Claude Code",
    MODE_AI_WEB: "AI-Web",
}

# Icon je Modus (liegt in assets/): Clawd die Pixel-Krabbe fuer Claude Code,
# das runde Chrome-Zeichen fuer den Web-Modus.
ICON_NAMES = {
    MODE_CLAUDE_CODE: "mode_claude_code.png",
    MODE_AI_WEB: "mode_ai_web.png",
}


def frontmost_bundle_id() -> str | None:
    """Bundle-ID der aktuell aktiven App (nur macOS), sonst None."""
    if sys.platform != "darwin":
        return None
    try:
        from AppKit import NSWorkspace

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None
        return app.bundleIdentifier()
    except Exception as ex:  # pragma: no cover — Systemgrenze
        log.warning("Vorder-App nicht ermittelbar: %s", ex)
        return None


def own_bundle_id() -> str | None:
    """Bundle-ID von Voice Flow selbst — um sie beim Fokus-Vergleich zu erkennen."""
    if sys.platform != "darwin":
        return None
    try:
        from Foundation import NSBundle

        return NSBundle.mainBundle().bundleIdentifier()
    except Exception:  # pragma: no cover — Systemgrenze
        return None


def activate_bundle_id(bundle_id: str | None) -> bool:
    """Holt die Ziel-App wieder nach vorne (nach einem Klick auf den Modus-Chip).

    Ohne das landet das Einfuegen in Voice Flow statt in Chrome.

    GEMESSEN 18.08.: `NSRunningApplication.activateWithOptions_` liefert hier
    False und Chrome kam auch nach 2,1 Sekunden nicht nach vorne (macOS laesst
    das Aktivieren fremder Apps so nicht mehr zu). `openApplicationAtURL` zieht
    dagegen in 0,15 s — und braucht, anders als AppleScript, keine
    Automations-Freigabe.
    """
    if not bundle_id or sys.platform != "darwin":
        return False
    try:
        from AppKit import NSWorkspace, NSWorkspaceOpenConfiguration

        workspace = NSWorkspace.sharedWorkspace()
        url = workspace.URLForApplicationWithBundleIdentifier_(bundle_id)
        if url is None:
            return False
        workspace.openApplicationAtURL_configuration_completionHandler_(
            url, NSWorkspaceOpenConfiguration.configuration(), None
        )
        return True
    except Exception as ex:  # pragma: no cover — Systemgrenze
        log.warning("Ziel-App %s nicht reaktivierbar: %s", bundle_id, ex)
        return False


def normalize_mode(value: str | None) -> str:
    """Unbekannter/fehlender Wert -> Default (Claude Code)."""
    return value if value in MODE_CYCLE else DEFAULT_MODE


def next_mode(mode: str) -> str:
    """Chip-Klick: zwischen den zwei Modi hin und her."""
    return MODE_AI_WEB if normalize_mode(mode) == MODE_CLAUDE_CODE else MODE_CLAUDE_CODE


def label(mode: str) -> str:
    return LABELS[normalize_mode(mode)]


def icon_path(mode: str) -> Path | None:
    """Pfad zum Modus-Icon, oder None wenn die Datei fehlt.

    Sucht neben dem Paket (Entwicklungsbaum) und im gebuendelten App-Ordner
    (PyInstaller legt Daten unter sys._MEIPASS ab).
    """
    name = ICON_NAMES[normalize_mode(mode)]
    kandidaten = []
    gebundelt = getattr(sys, "_MEIPASS", None)
    if gebundelt:
        kandidaten.append(Path(gebundelt) / "assets" / name)
    kandidaten.append(Path(__file__).resolve().parents[2] / "assets" / name)
    for pfad in kandidaten:
        if pfad.exists():
            return pfad
    log.warning("Modus-Icon %s nicht gefunden (gesucht: %s)", name, kandidaten)
    return None


def capture_marker(path: str, index: int, mode: str) -> str:
    """Marker-Text fuer EINEN Screenshot, passend zum Modus.

    claude_code: absoluter Pfad (Claude Code oeffnet die Datei selbst).
    ai_web: Nummer, die zur Einfuege-Reihenfolge der Bilder passt — der Pfad
    wuerde im Browser nur Platz fressen und Halluzinationen einladen.
    """
    name = Path(path).name
    if mode == MODE_AI_WEB:
        return f"(siehe Bild {index})"
    return f"(siehe {name} im Bucket: {path})"
