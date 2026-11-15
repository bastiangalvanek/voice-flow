"""15.11 Bastian: Musik-Knopf an der Pille — Ton beim Diktat an/aus, sonst alles wie vorher."""
from __future__ import annotations

import threading

from voice_flow.app import VoiceFlowApp
from voice_flow.mode_chip import MUSIC_BUTTON_GAP, MUSIC_BUTTON_SIZE, music_button_pos
from voice_flow.settings import Settings


class _FakeMute:
    def __init__(self):
        self.calls: list[str] = []

    def mute(self):
        self.calls.append("mute")

    def unmute(self):
        self.calls.append("unmute")


def _app(tmp_path, state):
    app = object.__new__(VoiceFlowApp)
    app.settings = Settings(tmp_path / "settings.json")
    app.audio_mute = _FakeMute()
    app.overlay = None
    app._state_lock = threading.Lock()
    app.state = state
    return app


def test_settings_musik_default_aus_und_persistiert(tmp_path):
    p = tmp_path / "settings.json"
    s = Settings(p)
    assert s.music_during_recording is False
    s.set_music_during_recording(True)
    assert Settings(p).music_during_recording is True
    s.set_music_during_recording(False)
    assert Settings(p).music_during_recording is False


def test_umschalten_im_diktat_wirkt_sofort(tmp_path):
    app = _app(tmp_path, VoiceFlowApp.STATE_RECORDING)
    assert app.toggle_music() is True
    assert app.toggle_music() is False
    assert app.audio_mute.calls == ["unmute", "mute"]


def test_umschalten_ohne_diktat_fasst_ton_nicht_an(tmp_path):
    app = _app(tmp_path, VoiceFlowApp.STATE_IDLE)
    app.toggle_music()
    app.toggle_music()
    assert app.audio_mute.calls == []


def test_mikro_bleibt_das_gewaehlte(tmp_path):
    """Musik an darf das Mikro nie wechseln (Bastian: Diktat immer uebers Poly)."""
    app = _app(tmp_path, VoiceFlowApp.STATE_IDLE)
    app.settings.set_audio_device("Poly VFOCUS2 Series")
    app.config = type("C", (), {"audio_device": None})()
    app.settings.set_music_during_recording(True)
    assert app._current_device() == "Poly VFOCUS2 Series"


def test_knopf_sitzt_links_am_chip():
    x, y = music_button_pos((700, 900, 140, 34))
    assert x + MUSIC_BUTTON_SIZE + MUSIC_BUTTON_GAP == 700
    assert y == 900


def _start_app(tmp_path, music_on: bool):
    app = _app(tmp_path, VoiceFlowApp.STATE_IDLE)
    app.settings.set_music_during_recording(music_on)
    app._hotkey_down = False
    app._tray_set = lambda *_: None
    app._ensure_session = lambda: None
    app.config = type("C", (), {"enable_sound": False, "hotkey": "f8"})()
    app.recorder = type("R", (), {"start": lambda self: None})()
    return app


def test_f8_mit_musik_an_schaltet_nicht_stumm(tmp_path):
    app = _start_app(tmp_path, music_on=True)
    app.on_hotkey_press()
    assert app.state == VoiceFlowApp.STATE_RECORDING
    assert app.audio_mute.calls == []


def test_f8_mit_musik_aus_schaltet_stumm_wie_vorher(tmp_path):
    app = _start_app(tmp_path, music_on=False)
    app.on_hotkey_press()
    assert app.audio_mute.calls == ["mute"]
