"""Capture-Session: ein Bucket-Ordner pro Aufnahme.

Sammelt Screenshots (shot_NN.png) und das Transkript, baut am Ende ein
bundle.md (Transkript + Markdown-Bildreferenzen). Reine Datei-/Pfad-Logik,
voll testbar.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

log = logging.getLogger(__name__)


class Session:
    def __init__(self, directory: Path):
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)
        self.shots: list[Path] = []
        # 27.06 Bastian: (offset_sekunden, pfad) je Shot der WAEHREND einer Aufnahme
        # gemacht wurde -> proportionale Marker-Platzierung im Transkript.
        self.captures: list[tuple[float, str]] = []
        self._transcript: str = ""

    def add_screenshot(self, img: Image.Image, offset: float | None = None) -> Path:
        path = self.dir / f"shot_{len(self.shots) + 1:02d}.png"
        img.save(path)
        self.shots.append(path)
        if offset is not None:
            self.captures.append((offset, str(path)))
        log.info("SHOT  %s", path.name)
        return path

    def set_transcript(self, text: str) -> None:
        self._transcript = text or ""
        (self.dir / "transcript.md").write_text(self._transcript, encoding="utf-8")

    def build_bundle(self) -> Path:
        lines: list[str] = []
        if self._transcript:
            lines.append(self._transcript.strip())
            lines.append("")
        for shot in self.shots:
            lines.append(f"![{shot.name}]({shot.name})")
        bundle = self.dir / "bundle.md"
        bundle.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return bundle


def new_session(base_dir: Path, now: str) -> Session:
    return Session(base_dir / now)
