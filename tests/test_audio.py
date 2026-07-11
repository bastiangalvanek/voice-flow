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
    # WICHTIG: voice_flow.audio hat sounddevice beim Import als `sd` gebunden.
    # sys.modules zu patchen reicht NICHT (rebindet audio.sd nicht) → Tests
    # wuerden echte Hardware oeffnen. Wir patchen das Modul-Attribut direkt →
    # hermetisch, kein Mikro noetig.
    import voice_flow.audio as audio_mod

    fake = types.ModuleType("sounddevice")
    fake.InputStream = _FakeStream  # type: ignore[attr-defined]
    fake.query_devices = lambda *a: ""  # type: ignore[attr-defined]
    # Gesetzter Windows-Default (Index 0) → Resolver nimmt ihn, ohne Auto-Pick.
    fake.default = types.SimpleNamespace(device=[0, 1])  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    monkeypatch.setattr(audio_mod, "sd", fake)
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


# --- Device-Resolution (F8-"Fehler": Error querying device -1) ---------------

# Bastians reales Layout: kein Windows-Default (-1). Poly = sein Wunsch-Mikro.
_REAL_DEVICES = [
    {"name": "Mikrofon (Realtek USB2.0 Audio)", "max_input_channels": 2, "default_samplerate": 44100.0},
    {"name": "Mikrofon (NexiGo N60 FHD Webcam Audio)", "max_input_channels": 1, "default_samplerate": 16000.0},
    {"name": "Lautsprecher (Realtek)", "max_input_channels": 0, "default_samplerate": 48000.0},
    {"name": "Kopfhoerer (Poly VFOCUS2 Series)", "max_input_channels": 1, "default_samplerate": 16000.0},
]


def test_find_input_by_name_matches_substring_case_insensitive():
    from voice_flow.audio import _find_input_by_name

    # "poly" (lowercase) matcht "Poly VFOCUS2" → Index 3, nicht ein Lautsprecher.
    assert _find_input_by_name(_REAL_DEVICES, "poly") == 3


def test_find_input_by_name_skips_output_devices():
    from voice_flow.audio import _find_input_by_name

    # "Realtek" kaeme auch beim Lautsprecher (Index 2) vor, aber der hat 0 Inputs.
    assert _find_input_by_name(_REAL_DEVICES, "Realtek") == 0


def test_find_input_by_name_returns_none_when_absent():
    from voice_flow.audio import _find_input_by_name

    assert _find_input_by_name(_REAL_DEVICES, "Rode NT") is None


def test_first_input_device_skips_outputs():
    from voice_flow.audio import _first_input_device

    outputs_then_mic = [
        {"name": "Lautsprecher", "max_input_channels": 0},
        {"name": "Mikrofon", "max_input_channels": 1},
    ]
    assert _first_input_device(outputs_then_mic) == 1
    assert _first_input_device([{"name": "Nur Output", "max_input_channels": 0}]) is None


def test_clean_device_name_extracts_bluetooth_friendly_name():
    from voice_flow.audio import clean_device_name

    # Roher WDM-KS-Name mit Treiberpfad UND Zeilenumbruch (Bastians Poly).
    raw = ("Kopfhörer (@System32\\drivers\\bthhfenum.sys,#2;%1 Hands-Free%0\r\n"
           ";(Poly VFOCUS2 Series))")
    assert clean_device_name(raw) == "Poly VFOCUS2 Series (Bluetooth)"


def test_clean_device_name_passthrough_and_whitespace():
    from voice_flow.audio import clean_device_name

    assert clean_device_name("Mikrofon (NexiGo N60 FHD Webcam Audio)") == \
        "Mikrofon (NexiGo N60 FHD Webcam Audio)"
    # Zeilenumbruch/Doppel-Space wird kollabiert.
    assert clean_device_name("Mikrofon\r\n  (Realtek)") == "Mikrofon (Realtek)"


def test_find_input_by_name_robust_to_newlines():
    from voice_flow.audio import _find_input_by_name

    devs = [
        {"name": "Kopfhörer (@System32\\drivers\\bthhfenum.sys\r\n;(Poly VFOCUS2 Series))",
         "max_input_channels": 1},
    ]
    # Gespeicherter Roh-Name (mit \r\n) matcht den Live-Namen trotz Whitespace-Diff.
    stored = "Kopfhörer (@System32\\drivers\\bthhfenum.sys ;(Poly VFOCUS2 Series))"
    assert _find_input_by_name(devs, stored) == 0


def _resolver_sd(monkeypatch, default_device, devices):
    """Stubbt das sounddevice-Modul in voice_flow.audio fuer den Resolver."""
    import voice_flow.audio as audio_mod

    fake = types.SimpleNamespace(
        default=types.SimpleNamespace(device=default_device),
        query_devices=lambda: devices,
    )
    monkeypatch.setattr(audio_mod, "sd", fake)


def test_resolve_uses_configured_index_verbatim(monkeypatch):
    from voice_flow.audio import resolve_input_device

    _resolver_sd(monkeypatch, [-1, 1], _REAL_DEVICES)
    assert resolve_input_device(7, 16000) == 7


def test_resolve_picks_device_by_name(monkeypatch):
    """Bastians Wunsch: VOICE_FLOW_AUDIO_DEVICE=Poly → sein Poly (Index 3)."""
    from voice_flow.audio import resolve_input_device

    _resolver_sd(monkeypatch, [-1, 1], _REAL_DEVICES)
    assert resolve_input_device("Poly", 16000) == 3


def test_resolve_name_miss_falls_back_to_windows_default(monkeypatch):
    from voice_flow.audio import resolve_input_device

    _resolver_sd(monkeypatch, [2, 1], _REAL_DEVICES)
    # "Rode" existiert nicht → Windows-Default (Index 2) greift.
    assert resolve_input_device("Rode", 16000) == 2


def test_resolve_uses_windows_default_when_set(monkeypatch):
    from voice_flow.audio import resolve_input_device

    _resolver_sd(monkeypatch, [3, 1], _REAL_DEVICES)
    assert resolve_input_device(None, 16000) == 3


def test_resolve_falls_back_to_first_mic_when_no_windows_default(monkeypatch):
    """DER Bug: Windows-Default-Input = -1 → frueher crash 'device -1'."""
    from voice_flow.audio import resolve_input_device

    _resolver_sd(monkeypatch, [-1, 1], _REAL_DEVICES)
    # Statt zu crashen: erstes Mikro (Index 0).
    assert resolve_input_device(None, 16000) == 0


def test_resolve_raises_clear_error_when_no_mic(monkeypatch):
    from voice_flow.audio import resolve_input_device

    outputs_only = [{"name": "Lautsprecher", "max_input_channels": 0, "default_samplerate": 48000.0}]
    _resolver_sd(monkeypatch, [-1, 1], outputs_only)
    with pytest.raises(RuntimeError, match="Kein Mikrofon"):
        resolve_input_device(None, 16000)
