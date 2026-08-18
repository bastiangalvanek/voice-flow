"""Freigaben: ablesen statt Dialoge feuern.

19.08 Bastian: "bei jedem F5/F3 kommt sogar das Voice-Flow-Fenster hoch, obwohl
ich es minimiert habe" — Ursache war, dass ein fehlgeschlagener Screenshot die
Systemeinstellungen oeffnete und dabei Voice Flow aktivierte. Diese Tests halten
den Pfad frei von jedem Fenster-Oeffner.
"""
from __future__ import annotations

import sys
import types

import pytest

from voice_flow import darwin_permissions as dp


def test_screenshot_ohne_freigabe_oeffnet_keine_fenster(monkeypatch):
    """Der Tastendruck-Pfad darf weder Dialog noch Systemeinstellungen ausloesen."""
    from voice_flow.app import VoiceFlowApp

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(dp, "screen_capture_ok", lambda: False)

    geoeffnet: list[str] = []
    monkeypatch.setattr(dp, "open_screen_capture_settings",
                        lambda: geoeffnet.append("einstellungen"))
    monkeypatch.setattr(dp, "request_screen_capture",
                        lambda: geoeffnet.append("dialog"))

    hinweise: list[str] = []
    app = VoiceFlowApp.__new__(VoiceFlowApp)
    app.overlay = types.SimpleNamespace(
        show_info=lambda text, ms=0: hinweise.append(text))

    assert app._bildschirm_freigabe_ok() is False
    assert geoeffnet == [], f"Tastendruck hat Fenster geoeffnet: {geoeffnet}"
    assert hinweise, "Ohne Freigabe muss wenigstens ein Hinweis erscheinen"
    assert "Bildschirmaufnahme" in hinweise[0]


def test_status_nennt_alle_drei_freigaben():
    status = dp.permission_status()
    assert set(status) == {"microphone", "accessibility", "screen"}
    assert all(isinstance(v, bool) for v in status.values())


def test_status_fragt_bedienungshilfen_ohne_dialog(monkeypatch):
    """Das Aufklappen des Fensters darf keinen Bedienungshilfen-Dialog werfen."""
    gefragt: list[bool] = []

    def falscher_ax(prompt: bool = True) -> bool:
        gefragt.append(prompt)
        return True

    monkeypatch.setattr(dp, "accessibility_ok", falscher_ax)
    monkeypatch.setattr(dp, "microphone_ok", lambda: True)
    monkeypatch.setattr(dp, "screen_capture_ok", lambda: True)
    monkeypatch.setattr(dp, "_IS_MAC", True)

    dp.permission_status()
    assert gefragt == [False], "permission_status darf nur ablesen, nie fragen"


def test_reparatur_loescht_den_eintrag_der_app(monkeypatch):
    """Gemessen 19.08: der Haken in der Liste stand, die App bekam trotzdem
    nichts — der Eintrag gehoerte zu einer aelteren Fassung. Genau den loescht
    die Reparatur, damit macOS neu fragen kann."""
    aufrufe: list[list[str]] = []

    class Ergebnis:
        returncode = 0
        stdout = "Successfully reset"
        stderr = ""

    monkeypatch.setattr(dp, "_IS_MAC", True)
    monkeypatch.setattr(dp.subprocess, "run",
                        lambda cmd, **kw: (aufrufe.append(cmd), Ergebnis())[1])

    assert dp.repair_screen_capture() is True
    assert aufrufe == [["tccutil", "reset", "ScreenCapture", "de.galvanek.voiceflow"]]


def test_heilung_ruehrt_eine_funktionierende_freigabe_nicht_an(monkeypatch, tmp_path):
    """Negativkontrolle: wirkt die Freigabe, darf nichts geloescht werden."""
    monkeypatch.setattr(dp, "_IS_MAC", True)
    monkeypatch.setattr(dp, "_MARKER", tmp_path / "marker")
    monkeypatch.setattr(dp, "screen_capture_ok", lambda: True)
    monkeypatch.setattr(dp, "repair_screen_capture",
                        lambda *a, **k: pytest.fail("gueltige Freigabe geloescht"))

    assert dp.heile_alte_bildschirm_freigabe() is False
    assert (tmp_path / "marker").exists(), "Merker fehlt — Heilung liefe erneut"


def test_heilung_putzt_die_tote_freigabe_genau_einmal(monkeypatch, tmp_path):
    monkeypatch.setattr(dp, "_IS_MAC", True)
    monkeypatch.setattr(dp, "_MARKER", tmp_path / "marker")
    monkeypatch.setattr(dp, "screen_capture_ok", lambda: False)
    laeufe: list[int] = []
    monkeypatch.setattr(dp, "repair_screen_capture",
                        lambda *a, **k: (laeufe.append(1), True)[1])

    assert dp.heile_alte_bildschirm_freigabe() is True
    assert dp.heile_alte_bildschirm_freigabe() is False, "lief ein zweites Mal"
    assert len(laeufe) == 1


def test_reparieren_knopf_holt_die_app_zurueck_in_die_liste(monkeypatch):
    """Nach dem Reset steht Voice Flow nicht mehr in der Liste. Der echte
    Handler muss deshalb den System-Dialog ausloesen — sonst gaebe es keinen
    Weg zurueck. Geprueft wird der Handler selbst, nicht eine Nachbildung."""
    pytest.importorskip("PyQt6")
    from voice_flow.control_window import build_control_window_class

    reihenfolge: list[str] = []
    monkeypatch.setattr(dp, "repair_screen_capture",
                        lambda *a, **k: (reihenfolge.append("reset"), True)[1])
    monkeypatch.setattr(dp, "request_screen_capture",
                        lambda: (reihenfolge.append("dialog"), False)[1])
    monkeypatch.setattr(dp, "open_screen_capture_settings",
                        lambda: reihenfolge.append("liste"))

    class Knopf:
        text = ""

        def setText(self, t: str) -> None:
            self.text = t

    fenster = types.SimpleNamespace(_fix_screen=Knopf())
    cls = build_control_window_class()
    cls._on_fix_screen(fenster)

    assert reihenfolge == ["reset", "dialog", "liste"], reihenfolge
    assert "neu starten" in fenster._fix_screen.text


def test_zeichen_ebene_reisst_den_fokus_nicht_an_sich():
    """19.08 Bastian: "wenn ich es minimiere, soll es minimiert bleiben".

    activateWindow() aktiviert die App Voice Flow — macOS holt dabei das
    minimierte Kontrollfenster hervor. Die Zeichen-Ebene darf das nicht tun.
    """
    import pathlib

    quelle = pathlib.Path(__file__).parent.parent / "src" / "voice_flow" / "annotate.py"
    text = quelle.read_text()
    aktiv = [z.strip() for z in text.splitlines()
             if "activateWindow()" in z and not z.strip().startswith("#")]
    assert aktiv == [], f"Zeichen-Ebene aktiviert die App: {aktiv}"
    assert "WA_ShowWithoutActivating" in text


def test_escape_schliesst_nur_wenn_wirklich_etwas_offen_ist():
    """ESC darf nichts tun, wenn keine Zeichen-Ebene offen ist — sonst wuerde
    jeder ESC-Druck irgendwo im System Arbeit ausloesen."""
    pytest.importorskip("PyQt6")
    from voice_flow.overlay_qt import RecordingOverlay

    overlay = RecordingOverlay.__new__(RecordingOverlay)
    overlay._annotate_bridge = None
    assert overlay.close_annotate() is False

    gesendet: list[str] = []
    overlay._annotate_bridge = types.SimpleNamespace(
        _overlay=None,
        sig_close=types.SimpleNamespace(emit=lambda: gesendet.append("zu")))
    assert overlay.close_annotate() is False
    assert gesendet == []

    overlay._annotate_bridge._overlay = object()
    assert overlay.close_annotate() is True
    assert gesendet == ["zu"]


def test_voice_flow_merkt_sich_nicht_selbst_als_ziel():
    """Gemessen 19.08.: nach dem Stopp sprang das minimierte Fenster auf, weil
    Voice Flow sich selbst als Ziel-App gemerkt und zurueckgeholt hatte."""
    from voice_flow.target_mode import ziel_merken

    eigen = "de.galvanek.voiceflow"
    assert ziel_merken(eigen, eigen) is None
    assert ziel_merken("com.google.Chrome", eigen) == "com.google.Chrome"
    # Ohne bekannte eigene ID (Nicht-Mac) bleibt alles wie gehabt.
    assert ziel_merken("com.google.Chrome", None) == "com.google.Chrome"
    assert ziel_merken(None, eigen) is None


def test_nachholen_laesst_zwischenablage_und_protokoll_in_ruhe(monkeypatch):
    """Der Knopf im Fenster darf weder das Kopierte wegnehmen noch die
    Protokollierung der laufenden App umstellen — beides taete main()."""
    import logging

    from voice_flow import recover

    monkeypatch.setattr(recover, "find_recoverable", lambda: [])
    monkeypatch.setattr(logging, "basicConfig",
                        lambda *a, **k: pytest.fail("basicConfig angefasst"))
    try:
        import pyperclip

        monkeypatch.setattr(pyperclip, "copy",
                            lambda *a, **k: pytest.fail("Zwischenablage ueberschrieben"))
    except ImportError:
        pass

    assert recover.nachholen() == (0, 0)


def test_fehlstarts_faerben_die_anzeige_nicht_rot(tmp_path, monkeypatch):
    """Eine 0,0-Minuten-Aufnahme ist kein fehlendes Transkript — sonst stuende
    die Zeile dauerhaft auf rot und die Frage "ist Transkript da?" waere wertlos.
    Eine echte Aufnahme muss aber weiterhin gezaehlt werden."""
    pytest.importorskip("PyQt6")
    from voice_flow.control_window import build_control_window_class

    fehlstart = tmp_path / "recording_leer_failed.wav"
    fehlstart.write_bytes(bytes(20_000))              # ~0,6 s Ton
    echt = tmp_path / "recording_echt_suspect.wav"
    echt.write_bytes(bytes(400_000))                  # ~12 s Ton

    from voice_flow import recording_storage
    monkeypatch.setattr(recording_storage, "list_pending_recordings",
                        lambda: [fehlstart, echt])

    cls = build_control_window_class()
    fenster = cls.__new__(cls)
    assert cls._offene_transkripte(fenster) == 1
