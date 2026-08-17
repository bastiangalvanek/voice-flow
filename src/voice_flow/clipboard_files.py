"""Mehrere DATEIEN in die Zwischenablage legen (nicht Text, nicht ein Bild).

Warum Dateien und nicht Bilddaten: Bilddaten kann die Zwischenablage nur EINMAL
halten — acht Screenshots wuerden acht Einfuege-Vorgaenge brauchen. Legt man
stattdessen Datei-URLs ab (genau das, was der Finder beim Kopieren macht),
liefert ein einziges Cmd+V dem Browser alle Bilder als DataTransfer.files.

GEMESSEN am 18.08.2026 in Bastians Chrome (Probe-Seite mit paste-Listener):
  3 Datei-URLs -> "files=3 | shot_01.png(image/png,406310B), shot_02.png…"
Und: liegen Text UND Dateien gleichzeitig drauf, liefert Chrome die Dateien und
verwirft den Text ("text=''"). Deshalb NIE mischen — erst Text einfuegen, dann
die Bilder als zweiter Vorgang (siehe paste.py).
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)


class ClipboardFilesUnsupported(RuntimeError):
    """Plattform kann keine Dateiliste in die Zwischenablage legen."""


def copy_files_to_clipboard(paths: list[str | Path]) -> int:
    """Legt die Dateien in die Zwischenablage. Gibt die Anzahl zurueck.

    Fehlende Dateien werden uebersprungen (und geloggt) statt alles zu kippen —
    ein einzelner geloeschter Screenshot darf das Diktat nicht verlieren.
    """
    existing = [Path(p).resolve() for p in paths if Path(p).exists()]
    skipped = len(paths) - len(existing)
    if skipped:
        log.warning("Zwischenablage: %d Datei(en) fehlen und werden uebersprungen.", skipped)
    if not existing:
        return 0

    if sys.platform == "darwin":
        _copy_darwin(existing)
    elif sys.platform == "win32":
        _copy_windows(existing)
    else:
        raise ClipboardFilesUnsupported(f"Dateien-Zwischenablage auf {sys.platform} nicht implementiert")
    return len(existing)


def _copy_darwin(paths: list[Path]) -> None:
    from AppKit import NSPasteboard
    from Foundation import NSURL

    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    urls = [NSURL.fileURLWithPath_(str(p)) for p in paths]
    if not pb.writeObjects_(urls):
        raise RuntimeError("NSPasteboard.writeObjects hat abgelehnt")


def _copy_windows(paths: list[Path]) -> None:
    """Windows-Pfad ueber PowerShell Set-Clipboard -LiteralPath (= CF_HDROP).

    NICHT auf Windows verifiziert (Portierung lief am Mac) — schlaegt der Aufruf
    fehl, wirft er laut, damit paste.py auf Text-only zurueckfaellt statt still
    nichts zu tun.
    """
    args = ",".join(f"'{str(p)}'" for p in paths)
    cmd = ["powershell", "-NoProfile", "-Command", f"Set-Clipboard -LiteralPath {args}"]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if res.returncode != 0:
        raise RuntimeError(f"Set-Clipboard fehlgeschlagen: {res.stderr.strip()[:200]}")
