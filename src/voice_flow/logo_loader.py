from __future__ import annotations

from pathlib import Path

# voice-flow/ Wurzel (zwei Ebenen ueber src/voice_flow/logo_loader.py)
_ROOT = Path(__file__).resolve().parents[2]

# 27.06 Bastian: Logo muss in der Pille IMMER erscheinen — egal wie/wo installiert.
# Frueher hing das Logo an _ROOT/logo.png. Das funktioniert nur, wenn man AUS dem
# Repo-Ordner startet. Bei `pip install .` (nicht-editable), Start aus anderem CWD
# oder einer spaeteren EXE zeigt parents[2] ins site-packages -> Logo weg.
#
# Fix: das Branding liegt jetzt ZUSAETZLICH als Package-Asset (src/voice_flow/assets/)
# und reist mit jeder Installation mit. Aufloesungs-Reihenfolge:
#   1. _ROOT/logo.png         -> erlaubt eigenes Branding (Datei im Ordner austauschen)
#   2. Package-Asset          -> GARANTIERT vorhanden, install-unabhaengig
#   3. Original-Flocke (Root + Package) als letzter Fallback
_ASSETS = Path(__file__).resolve().parent / "assets"

LOGO_CANDIDATES = [
    _ROOT / "logo.png",
    _ASSETS / "logo.png",
    _ROOT / "LinkedIn Galvanek Profil Flocke (2).png",
    _ASSETS / "logo-original.png",
]

# .ico bevorzugt aus Root (von make_icon.py generiert/aktualisiert),
# sonst das mitgelieferte Package-Asset (scharfes Taskleisten-Icon ohne Setup).
ICON_CANDIDATES = [
    _ROOT / "voice-flow.ico",
    _ASSETS / "voice-flow.ico",
]


def resolve_logo_path() -> Path | None:
    """Erster existierender Logo-Kandidat, sonst None (Fallback-Icon)."""
    for candidate in LOGO_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def resolve_icon_path() -> Path | None:
    """voice-flow.ico (Multi-Size, scharf in Taskleiste/Fenster), sonst None."""
    for candidate in ICON_CANDIDATES:
        if candidate.exists():
            return candidate
    return None
