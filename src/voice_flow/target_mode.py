"""Ziel-Modus: bekommt der Empfaenger Datei-PFADE oder echte BILDER?

Hintergrund (18.08 Bastian): Claude Code liest die Screenshots selbst von der
Platte — ein Marker mit absolutem Pfad ist dort das Beste, was man einfuegen
kann. Ein Web-Chat (Lovable, ChatGPT, claude.ai, Gemini) hat das Verzeichnis
NICHT: dort ist der Pfad wertlos, dort muessen die Bilder als Dateien in die
Zwischenablage und per zweitem Cmd+V hinterher.

Zwei Modi, drei Einstellungen: "claude_code", "ai_web" und "auto" (entscheidet
anhand der Vorder-App). Reine Logik, keine I/O — bis auf frontmost_bundle_id(),
das als einzige Funktion das System fragt.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

MODE_CLAUDE_CODE = "claude_code"
MODE_AI_WEB = "ai_web"
SETTING_AUTO = "auto"

# Reihenfolge des Chip-Klicks: Auto -> Claude Code -> AI-Web -> Auto.
SETTING_CYCLE = (SETTING_AUTO, MODE_CLAUDE_CODE, MODE_AI_WEB)

LABELS = {
    SETTING_AUTO: "Auto",
    MODE_CLAUDE_CODE: "Claude Code",
    MODE_AI_WEB: "AI-Web",
}

# Apps, deren Eingabefeld KEINEN Dateisystem-Zugriff hat -> Bilder einfuegen.
# Browser + die Desktop-Huellen der Web-Chats (die sind innen auch nur Web).
WEB_APP_BUNDLE_IDS = frozenset({
    "com.google.chrome",
    "com.google.chrome.canary",
    "com.google.chrome.beta",
    "com.apple.safari",
    "com.apple.safaritechnologypreview",
    "com.microsoft.edgemac",
    "com.microsoft.edge",
    "org.mozilla.firefox",
    "org.mozilla.firefoxdeveloperedition",
    "com.brave.browser",
    "company.thebrowser.browser",     # Arc
    "company.thebrowser.dia",          # Dia
    "com.operasoftware.opera",
    "com.vivaldi.vivaldi",
    "com.openai.chat",                 # ChatGPT-Desktop
    "com.anthropic.claudefordesktop",  # Claude-Desktop
    "com.google.gemini.electron",
})


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
    """Bundle-ID von Voice Flow selbst — um sie bei der Auto-Erkennung zu ignorieren."""
    if sys.platform != "darwin":
        return None
    try:
        from Foundation import NSBundle

        return NSBundle.mainBundle().bundleIdentifier()
    except Exception:  # pragma: no cover — Systemgrenze
        return None


def activate_bundle_id(bundle_id: str | None) -> bool:
    """Holt die Ziel-App wieder nach vorne (nach einem Klick auf den Modus-Chip).

    Ohne das koennte das Einfuegen in Voice Flow statt in Chrome landen.
    """
    if not bundle_id or sys.platform != "darwin":
        return False
    try:
        from AppKit import NSRunningApplication, NSApplicationActivateIgnoringOtherApps

        apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id)
        if not apps:
            return False
        return bool(apps[0].activateWithOptions_(NSApplicationActivateIgnoringOtherApps))
    except Exception as ex:  # pragma: no cover — Systemgrenze
        log.warning("Ziel-App %s nicht reaktivierbar: %s", bundle_id, ex)
        return False


def resolve_mode(setting: str, bundle_id: str | None) -> str:
    """Einstellung + Vorder-App -> effektiver Modus.

    Feste Einstellung gewinnt immer. Bei "auto" entscheidet die Vorder-App:
    bekannter Web-Client -> ai_web, alles andere (Terminal, Editor, unbekannt)
    -> claude_code. Unbekannt absichtlich auf claude_code: ein zu viel
    eingefuegter Pfad ist harmlos, ein Bilderschwall in eine fremde App nicht.
    """
    if setting in (MODE_CLAUDE_CODE, MODE_AI_WEB):
        return setting
    if bundle_id and bundle_id.lower() in WEB_APP_BUNDLE_IDS:
        return MODE_AI_WEB
    return MODE_CLAUDE_CODE


def next_setting(setting: str) -> str:
    """Naechster Wert im Chip-Klick-Zyklus (unbekannter Wert -> Auto)."""
    try:
        idx = SETTING_CYCLE.index(setting)
    except ValueError:
        return SETTING_AUTO
    return SETTING_CYCLE[(idx + 1) % len(SETTING_CYCLE)]


def chip_label(setting: str, bundle_id: str | None) -> str:
    """Text fuer den Modus-Chip: bei Auto zeigt er, worauf es hinauslaeuft."""
    if setting == SETTING_AUTO:
        return f"Auto · {LABELS[resolve_mode(setting, bundle_id)]}"
    return LABELS.get(setting, LABELS[SETTING_AUTO])


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
