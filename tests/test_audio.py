"""AudioRecorder Tests.

Wir stubben sounddevice komplett — kein echtes Mikro im Test.
Test: WAV-Header korrekt, RMS-Level wird im Callback aktualisiert,
Lifecycle (start/stop/start) clean.
"""
from __future__ import annotations

import sys
import types

import numpy as np
import pytest


class _FakeStream:
    def __init__(self, **kwargs):
        self.callback = kwargs.get("callback")
        self.started = False
        self.closed = False

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def close(self):
        self.closed = True


@pytest.fixture
def fake_sounddevice(monkeypatch):
    fake = types.ModuleType("sounddevice")
    fake.InputStream = _FakeStream  # type: ignore[attr-defined]
    fake.query_devices = lambda: ""  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    yield fake


def test_recorder_lifecycle(fake_sounddevice):
    from voice_flow.audio import AudioRecorder

    r = AudioRecorder(sample_rate=16000, channels=1)
    r.start()

    # Simuliere ein paar Audio-Frames durch direkten Callback-Aufruf
    frame = np.zeros((512, 1), dtype=np.int16)
    r._callback(frame, 512, None, None)
    r._callback(frame, 512, None, None)

    wav_bytes = r.stop()

    # WAV-Header: "RIFF...WAVE"
    assert wav_bytes[:4] == b"RIFF"
    assert wav_bytes[8:12] == b"WAVE"
    # Dauer: 1024 samples / 16000 = 0.064s
    assert 0.06 <= r.duration_seconds <= 0.07


def test_recorder_stop_without_start_raises(fake_sounddevice):
    from voice_flow.audio import AudioRecorder

    r = AudioRecorder()
    with pytest.raises(RuntimeError, match="without start"):
        r.stop()


def test_recorder_start_twice_raises(fake_sounddevice):
    from voice_flow.audio import AudioRecorder

    r = AudioRecorder()
    r.start()
    with pytest.raises(RuntimeError, match="already recording"):
        r.start()


def test_level_updates_on_loud_audio(fake_sounddevice):
    from voice_flow.audio import AudioRecorder

    r = AudioRecorder()
    r.start()
    assert r.current_level == 0.0

    # Lautes Audio: half-amplitude int16 noise → RMS ~16000 → /32768 *4 → clamped 1.0
    loud = (np.ones((1024, 1), dtype=np.int16) * 16000)
    for _ in range(5):  # Smoothing benoetigt mehrere Frames
        r._callback(loud, 1024, None, None)
    assert r.current_level > 0.5, f"loud level should be high, got {r.current_level}"

    # Stilles Audio: alles 0 → RMS 0 → level decays
    silent = np.zeros((1024, 1), dtype=np.int16)
    for _ in range(10):
        r._callback(silent, 1024, None, None)
    assert r.current_level < 0.1, f"silent level should decay, got {r.current_level}"


def test_level_resets_on_new_recording(fake_sounddevice):
    from voice_flow.audio import AudioRecorder

    r = AudioRecorder()
    r.start()
    loud = (np.ones((1024, 1), dtype=np.int16) * 16000)
    for _ in range(5):
        r._callback(loud, 1024, None, None)
    r.stop()

    r.start()
    assert r.current_level == 0.0
    r.stop()


def test_empty_frames_returns_empty_wav(fake_sounddevice):
    from voice_flow.audio import AudioRecorder

    r = AudioRecorder()
    r.start()
    wav = r.stop()
    # Kein callback aufgerufen → keine frames → leere bytes
    assert wav == b""
    assert r.duration_seconds == 0.0
