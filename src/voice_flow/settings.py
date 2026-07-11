"""Persistente Nutzer-Einstellungen (~/.voice-flow/settings.json).

Aktuell: das gewaehlte Mikrofon. Gespeichert wird der GERAETE-NAME (nicht der
Index) — Indizes wackeln bei jedem An-/Abstecken, der Name bleibt stabil. Der
Resolver in audio.py matcht spaeter per Name zurueck auf den aktuellen Index.

Bewusst winzig und dumm: laden = JSON lesen, setzen = schreiben. Kein Cache-
Invalidations-Zauber, keine Migrationen. Schlaegt IO fehl, faellt Voice Flow auf
den Windows-Standard zurueck (siehe resolve_input_device) statt zu crashen.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

SETTINGS_PATH = Path.home() / ".voice-flow" / "settings.json"


class Settings:
    def __init__(self, path: Path = SETTINGS_PATH):
        self._path = path
        self._data: dict = self._load()

    def _load(self) -> dict:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except Exception as ex:
            log.warning("settings.json nicht lesbar (%s) — nutze Defaults.", ex)
            return {}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as ex:
            log.warning("settings.json nicht speicherbar (%s).", ex)

    @property
    def audio_device(self) -> str | None:
        """Gewaehlter Mikrofon-Name, oder None (dann: Windows-Standard)."""
        value = self._data.get("audio_device")
        return value if isinstance(value, str) and value.strip() else None

    def set_audio_device(self, name: str | None) -> None:
        if name:
            self._data["audio_device"] = name
        else:
            self._data.pop("audio_device", None)
        self._save()
