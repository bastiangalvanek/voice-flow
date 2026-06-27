import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock

import voice_flow.app as app_mod
from voice_flow.app import VoiceFlowApp
from voice_flow.config import Config


def _app():
    cfg = Config(
        openai_api_key="x",
        hotkey_mode="toggle",
        enable_overlay=False,
        enable_audio_mute=False,
        enable_sound=False,
        # Session-Buckets in einen Wegwerf-Ordner, nicht ins echte Home.
        sessions_dir=Path(tempfile.mkdtemp(prefix="vf-toggle-test-")),
    )
    app = VoiceFlowApp.__new__(VoiceFlowApp)
    app.config = cfg
    app.recorder = MagicMock()
    app.recorder.duration_seconds = 1.0
    app.recorder.stop.return_value = b"wavbytes"
    app.audio_mute = None
    app.overlay = None
    app.tray = None
    app._state_lock = threading.Lock()
    app.state = VoiceFlowApp.STATE_IDLE
    app._hotkey_down = False
    app._auth_error_shown = False
    app._last_toggle = 0.0
    app.session = None
    app._record_start = None
    return app


def _clock(monkeypatch, times):
    """Deterministische time.monotonic-Sequenz fuer on_hotkey_toggle.

    Ein Start-Toggle verbraucht zwei Ticks: erst den Debounce-Wert in
    on_hotkey_toggle, dann _record_start in on_hotkey_press (27.06: Zeitachse
    fuer proportionale Screenshot-Marker). Der zusaetzliche Tick wird hier
    automatisch hinter jeden Start-Wert geschoben (siehe je Test).
    """
    monkeypatch.setattr(app_mod.time, "monotonic", MagicMock(side_effect=list(times)))


def test_toggle_idle_starts_recording(monkeypatch):
    # [debounce, _record_start]
    _clock(monkeypatch, [100.0, 100.0])
    app = _app()
    app.on_hotkey_toggle()
    assert app.state == VoiceFlowApp.STATE_RECORDING
    app.recorder.start.assert_called_once()


def test_toggle_recording_stops(monkeypatch):
    monkeypatch.setattr(app_mod.threading, "Thread", MagicMock())
    # [debounce-start, _record_start, debounce-stop]  (Stop ruft kein monotonic)
    _clock(monkeypatch, [100.0, 100.0, 100.5])  # 500ms spaeter
    app = _app()
    app.on_hotkey_toggle()                  # idle -> recording
    app.on_hotkey_toggle()                  # recording -> processing
    assert app.state == VoiceFlowApp.STATE_PROCESSING
    app.recorder.stop.assert_called_once()


def test_toggle_allows_quick_stop_at_150ms(monkeypatch):
    # Critic P1: ein bewusster schneller Stop (150ms nach Start) darf NICHT
    # vom Backstop-Debounce verschluckt werden.
    monkeypatch.setattr(app_mod.threading, "Thread", MagicMock())
    # [debounce-start, _record_start, debounce-stop]
    _clock(monkeypatch, [100.0, 100.0, 100.15])
    app = _app()
    app.on_hotkey_toggle()                  # start
    app.on_hotkey_toggle()                  # stop bei +150ms
    assert app.state == VoiceFlowApp.STATE_PROCESSING
    app.recorder.stop.assert_called_once()


def test_toggle_backstop_swallows_same_instant(monkeypatch):
    # Zwei Aufrufe im selben Augenblick (<50ms) -> zweiter verschluckt.
    # [debounce-start, _record_start, debounce-2nd (verschluckt, kein press)]
    _clock(monkeypatch, [100.0, 100.0, 100.02])
    app = _app()
    app.on_hotkey_toggle()
    app.on_hotkey_toggle()
    assert app.state == VoiceFlowApp.STATE_RECORDING
    app.recorder.start.assert_called_once()
