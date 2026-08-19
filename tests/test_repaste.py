"""Das letzte Diktat noch einmal einfuegen — Text, dann Bilder.

19.08 Bastian: "Strg+V aus einer Chrome-Session sollte auch in Kaskade pasten,
wenn Bilder mal nicht mitgeliefert wurden oder man im falschen Tab war: wieder
Strg+V und dann erst Text und danach die Bilder."
"""
from __future__ import annotations

import types

import pytest

from voice_flow import target_mode
from voice_flow.app import VoiceFlowApp


def _app(monkeypatch, mode: str, reihenfolge: list):
    """VoiceFlowApp ohne __init__ — nur die Einfuege-Logik."""
    import voice_flow.app as app_mod

    monkeypatch.setattr(app_mod, "paste_to_active_window",
                        lambda text, **kw: reihenfolge.append(("text", text)))
    monkeypatch.setattr(app_mod, "paste_files_to_active_window",
                        lambda pfade: (reihenfolge.append(("bilder", list(pfade))),
                                       len(pfade))[1])

    app = VoiceFlowApp.__new__(VoiceFlowApp)
    app.config = types.SimpleNamespace(enable_clipboard_restore=False)
    app.overlay = None
    app.resolved_paste_mode = lambda: mode
    app._warte_auf_losgelassene_tasten = lambda *a, **k: None
    return app


def test_wiederholen_fuegt_erst_text_dann_bilder_ein(monkeypatch):
    reihenfolge: list = []
    app = _app(monkeypatch, target_mode.MODE_AI_WEB, reihenfolge)
    app._letztes_diktat = {
        "text": "Erster Satz. Zweiter Satz.",
        "shots": ["/tmp/shot_01.png", "/tmp/shot_02.png"],
        "captures": [(1.0, "/tmp/shot_01.png"), (2.0, "/tmp/shot_02.png")],
        "duration": 4.0,
    }

    app.on_repaste_hotkey()

    assert [art for art, _ in reihenfolge] == ["text", "bilder"], reihenfolge
    assert reihenfolge[1][1] == ["/tmp/shot_01.png", "/tmp/shot_02.png"]


def test_alle_bilder_gehen_in_einem_vorgang_mit(monkeypatch):
    """Kein Limit im Programm: zwanzig Screenshots sind ein einziger Vorgang."""
    reihenfolge: list = []
    app = _app(monkeypatch, target_mode.MODE_AI_WEB, reihenfolge)
    viele = [f"/tmp/shot_{i:02d}.png" for i in range(1, 21)]
    app._letztes_diktat = {"text": "Text.", "shots": viele,
                           "captures": [(float(i), p) for i, p in enumerate(viele)],
                           "duration": 30.0}

    app.on_repaste_hotkey()

    bilder = [nutzlast for art, nutzlast in reihenfolge if art == "bilder"]
    assert len(bilder) == 1, "Bilder duerfen nicht einzeln eingefuegt werden"
    assert len(bilder[0]) == 20


def test_claude_code_modus_fuegt_keine_bilder_ein(monkeypatch):
    """Dort zaehlt der Pfad im Text — Bilddaten waeren dort sinnlos."""
    reihenfolge: list = []
    app = _app(monkeypatch, target_mode.MODE_CLAUDE_CODE, reihenfolge)
    app._letztes_diktat = {"text": "Text.", "shots": ["/tmp/shot_01.png"],
                           "captures": [(1.0, "/tmp/shot_01.png")], "duration": 2.0}

    app.on_repaste_hotkey()

    assert [art for art, _ in reihenfolge] == ["text"]


def test_marker_richten_sich_nach_dem_modus_von_JETZT(monkeypatch):
    """Fuer Claude Code diktiert, dann in den Browser wiederholt: der Text darf
    dort keine Dateipfade tragen, sondern Bildnummern."""
    reihenfolge: list = []
    app = _app(monkeypatch, target_mode.MODE_AI_WEB, reihenfolge)
    app._letztes_diktat = {"text": "Erster Satz. Zweiter Satz.",
                           "shots": ["/tmp/shot_01.png"],
                           "captures": [(1.0, "/tmp/shot_01.png")], "duration": 4.0}

    app.on_repaste_hotkey()

    text = reihenfolge[0][1]
    assert "Bild 1" in text
    assert "/tmp/shot_01.png" not in text, "Dateipfad im Browser ist wertlos"


def test_ohne_diktat_passiert_nichts(monkeypatch):
    reihenfolge: list = []
    app = _app(monkeypatch, target_mode.MODE_AI_WEB, reihenfolge)
    hinweise: list = []
    app.overlay = types.SimpleNamespace(show_info=lambda t, ms=0: hinweise.append(t))

    app.on_repaste_hotkey()

    assert reihenfolge == []
    assert hinweise and "Noch kein Diktat" in hinweise[0]


def test_wartet_bis_die_zusatztasten_los_sind(monkeypatch):
    """Das Kuerzel haelt Umschalt+Befehl. Sofortiges Befehl+V kaeme in Chrome als
    Befehl+Umschalt+V an — "als Klartext einfuegen" statt Einfuegen."""
    reihenfolge: list = []
    app = _app(monkeypatch, target_mode.MODE_AI_WEB, reihenfolge)
    gewartet: list = []
    app._warte_auf_losgelassene_tasten = lambda *a, **k: gewartet.append(True)
    app._letztes_diktat = {"text": "Text.", "shots": [], "captures": [], "duration": 1.0}

    app.on_repaste_hotkey()

    assert gewartet == [True], "Ohne Warten kollidiert das Kuerzel mit dem Einfuegen"
    assert [art for art, _ in reihenfolge] == ["text"]
