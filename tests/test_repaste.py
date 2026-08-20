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


# ---------- Cmd+V als Kaskade (20.08.) ----------


def test_cmd_v_kaskadiert_nur_wenn_alles_stimmt():
    """Ein faelschlich uebernommenes Cmd+V = "Einfuegen geht nicht mehr" —
    der schlimmste Fehler dieses Features. Jede Abweichung -> native."""
    from voice_flow.smart_paste import soll_kaskadieren

    # Der einzige Ja-Fall: AI-Web, Diktat da, Zwischenablage unveraendert.
    assert soll_kaskadieren("ai_web", True, 42, 42, False) is True

    assert soll_kaskadieren("claude_code", True, 42, 42, False) is False
    assert soll_kaskadieren("ai_web", False, 42, 42, False) is False
    assert soll_kaskadieren("ai_web", True, 43, 42, False) is False, \
        "Bastian hat etwas anderes kopiert — Cmd+V muss DAS einfuegen"
    assert soll_kaskadieren("ai_web", True, None, 42, False) is False
    assert soll_kaskadieren("ai_web", True, 42, None, False) is False
    assert soll_kaskadieren("ai_web", True, 42, 42, True) is False, \
        "das eigene Cmd+V der laufenden Kaskade darf nie gefangen werden"


def test_on_cmd_v_kehrt_bei_fehler_immer_nativ_zurueck(monkeypatch):
    """Wirft die Entscheidung, laeuft das native Einfuegen unangetastet."""
    from voice_flow import smart_paste

    app = VoiceFlowApp.__new__(VoiceFlowApp)
    app.resolved_paste_mode = lambda: (_ for _ in ()).throw(RuntimeError("kaputt"))
    assert app.on_cmd_v() is False

    # Und: nicht scharf gestellt -> False, ohne Thread.
    app.resolved_paste_mode = lambda: "ai_web"
    app._letztes_diktat = {"text": "x", "shots": [], "captures": [], "duration": 1.0}
    monkeypatch.setattr(smart_paste, "clipboard_stand", lambda: 7)
    app._clipboard_stand = None
    assert app.on_cmd_v() is False


def test_on_cmd_v_uebernimmt_und_sperrt_sofort(monkeypatch):
    """Uebernahme muss das Wiederholungs-Echo SOFORT sperren — nicht erst wenn
    der Thread anlaeuft, sonst faengt das synthetische Cmd+V sich selbst."""
    import threading as th

    from voice_flow import smart_paste

    app = VoiceFlowApp.__new__(VoiceFlowApp)
    app.resolved_paste_mode = lambda: "ai_web"
    app._letztes_diktat = {"text": "x", "shots": [], "captures": [], "duration": 1.0}
    app._clipboard_stand = 7
    monkeypatch.setattr(smart_paste, "clipboard_stand", lambda: 7)
    gestartet: list = []
    monkeypatch.setattr(th, "Thread",
                        lambda **kw: types.SimpleNamespace(start=lambda: gestartet.append(kw)))

    assert app.on_cmd_v() is True
    assert app._kaskade_aktiv is True, "Sperre muss VOR dem Thread stehen"
    assert len(gestartet) == 1
    # Zweites Cmd+V waehrend die Kaskade laeuft: durchlassen.
    assert app.on_cmd_v() is False


def test_kaskade_merkt_sich_den_zwischenablage_stand(monkeypatch):
    """Nur im AI-Web-Modus wird scharf gestellt; Claude Code entwaffnet."""
    import voice_flow.app as app_mod
    from voice_flow import smart_paste

    monkeypatch.setattr(app_mod, "paste_to_active_window", lambda *a, **k: None)
    monkeypatch.setattr(app_mod, "paste_files_to_active_window", lambda p: len(p))
    monkeypatch.setattr(smart_paste, "clipboard_stand", lambda: 99)

    app = VoiceFlowApp.__new__(VoiceFlowApp)
    app.config = types.SimpleNamespace(enable_clipboard_restore=False)
    app.overlay = None

    app._kaskade_einfuegen("Text.", [], [], 1.0, target_mode.MODE_AI_WEB)
    assert app._clipboard_stand == 99

    app._kaskade_einfuegen("Text.", [], [], 1.0, target_mode.MODE_CLAUDE_CODE)
    assert app._clipboard_stand is None


def test_web_pause_liegt_zwischen_text_und_bildern(monkeypatch):
    """20.08: 13 Bilder kamen bei Lovable nicht an — Text und Dateiliste trafen
    0,42 s auseinander ein. Die Kaskade muss der Web-App Luft lassen, und zwar
    NACH dem Text und VOR den Bildern (davor waere sie wirkungslos)."""
    import voice_flow.app as app_mod

    ablauf: list = []
    monkeypatch.setattr(app_mod, "paste_to_active_window",
                        lambda *a, **k: ablauf.append("text"))
    monkeypatch.setattr(app_mod, "paste_files_to_active_window",
                        lambda p: (ablauf.append("bilder"), len(p))[1])
    monkeypatch.setattr(app_mod.time, "sleep",
                        lambda s: ablauf.append(("pause", s)))

    app = VoiceFlowApp.__new__(VoiceFlowApp)
    app.config = types.SimpleNamespace(enable_clipboard_restore=False)
    app.overlay = None
    app._kaskade_einfuegen("Text.", ["/tmp/shot_01.png"],
                           [(1.0, "/tmp/shot_01.png")], 2.0,
                           target_mode.MODE_AI_WEB)

    assert ablauf == ["text", ("pause", app_mod.WEB_BILDER_PAUSE_SEC), "bilder"]

    # Claude-Code-Modus: keine Bilder, keine Pause.
    ablauf.clear()
    app._kaskade_einfuegen("Text.", ["/tmp/shot_01.png"],
                           [(1.0, "/tmp/shot_01.png")], 2.0,
                           target_mode.MODE_CLAUDE_CODE)
    assert ablauf == ["text"]


def test_ab_fuenf_bildern_kommt_der_sende_hinweis(monkeypatch):
    """"Eingefuegt" heisst nur uebergeben — bei vielen Bildern muss der Hinweis
    kommen, nicht zu senden bevor alle Vorschauen geladen sind."""
    import voice_flow.app as app_mod

    monkeypatch.setattr(app_mod, "paste_to_active_window", lambda *a, **k: None)
    monkeypatch.setattr(app_mod, "paste_files_to_active_window", lambda p: len(p))
    monkeypatch.setattr(app_mod.time, "sleep", lambda s: None)

    hinweise: list = []
    app = VoiceFlowApp.__new__(VoiceFlowApp)
    app.config = types.SimpleNamespace(enable_clipboard_restore=False)
    app.overlay = types.SimpleNamespace(show_info=lambda t, ms=0: hinweise.append(t))

    fuenf = [f"/tmp/shot_{i:02d}.png" for i in range(1, 6)]
    app._kaskade_einfuegen("Text.", fuenf,
                           [(float(i), p) for i, p in enumerate(fuenf)], 9.0,
                           target_mode.MODE_AI_WEB)
    assert any("Vorschauen" in h for h in hinweise), hinweise

    hinweise.clear()
    app._kaskade_einfuegen("Text.", fuenf[:2],
                           [(1.0, fuenf[0]), (2.0, fuenf[1])], 4.0,
                           target_mode.MODE_AI_WEB)
    assert hinweise == [], "bei 2 Bildern kein Hinweis-Spam"


def test_cmd_v_im_eigenen_fenster_bleibt_nativ(monkeypatch):
    """Ist Voice Flow selbst vorn (Kontrollfenster angeklickt), wuerde die
    Kaskade ins eigene Fenster verpuffen — durchlassen (gemessen 20.08)."""
    from voice_flow import smart_paste

    app = VoiceFlowApp.__new__(VoiceFlowApp)
    app.resolved_paste_mode = lambda: "ai_web"
    app._letztes_diktat = {"text": "x", "shots": [], "captures": [], "duration": 1.0}
    app._clipboard_stand = 7
    monkeypatch.setattr(smart_paste, "clipboard_stand", lambda: 7)
    monkeypatch.setattr(target_mode, "own_bundle_id", lambda: "de.galvanek.voiceflow")
    monkeypatch.setattr(target_mode, "frontmost_bundle_id",
                        lambda: "de.galvanek.voiceflow")

    assert app.on_cmd_v() is False

    monkeypatch.setattr(target_mode, "frontmost_bundle_id",
                        lambda: "com.google.Chrome")
    import threading as th
    monkeypatch.setattr(th, "Thread",
                        lambda **kw: types.SimpleNamespace(start=lambda: None))
    assert app.on_cmd_v() is True
