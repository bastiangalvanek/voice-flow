"""Dateien-Zwischenablage: Einstellung persistieren + echtes macOS-Pasteboard.

Der Pasteboard-Test laeuft NUR auf macOS und schreibt wirklich in die
Zwischenablage — das ist beabsichtigt: genau dieser Schritt ist der Kern des
AI-Web-Modus, und ein Mock haette am 18.08 nicht gezeigt, dass Chrome bei
gemischtem Inhalt den Text verwirft.
"""
from __future__ import annotations

import sys

import pytest
from PIL import Image

from voice_flow.clipboard_files import copy_files_to_clipboard
from voice_flow.settings import Settings
from voice_flow.target_mode import MODE_AI_WEB, SETTING_AUTO


def _png(path, color="red"):
    Image.new("RGB", (8, 8), color).save(path)
    return path


def test_fehlende_dateien_werden_uebersprungen_statt_alles_zu_kippen(tmp_path):
    real = _png(tmp_path / "shot_01.png")
    fehlt = tmp_path / "shot_99.png"
    count = copy_files_to_clipboard([real, fehlt])
    assert count == 1


def test_leere_liste_macht_nichts():
    assert copy_files_to_clipboard([]) == 0


@pytest.mark.skipif(sys.platform != "darwin", reason="NSPasteboard nur auf macOS")
def test_drei_dateien_liegen_als_drei_pasteboard_items(tmp_path):
    from AppKit import NSPasteboard

    paths = [_png(tmp_path / f"shot_{i:02d}.png") for i in (1, 2, 3)]
    assert copy_files_to_clipboard(paths) == 3

    pb = NSPasteboard.generalPasteboard()
    items = pb.pasteboardItems()
    assert len(items) == 3, "ein Item pro Bild — sonst kommt nur ein Bild im Browser an"
    for item in items:
        assert "public.file-url" in list(item.types())


def test_paste_mode_wird_persistiert_und_faellt_bei_muell_auf_auto(tmp_path):
    path = tmp_path / "settings.json"
    s = Settings(path=path)
    assert s.paste_mode == SETTING_AUTO  # Default

    s.set_paste_mode(MODE_AI_WEB)
    assert Settings(path=path).paste_mode == MODE_AI_WEB  # ueberlebt Neustart

    path.write_text('{"paste_mode": "quatsch"}', encoding="utf-8")
    assert Settings(path=path).paste_mode == SETTING_AUTO
