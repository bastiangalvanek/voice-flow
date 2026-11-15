"""15.11 Bastian: Musik-Knopf an der Pille — Ton beim Diktat an/aus."""
from __future__ import annotations

from voice_flow import audio
from voice_flow.audio import is_headset_mic, wired_alternative
from voice_flow.mode_chip import MUSIC_BUTTON_GAP, MUSIC_BUTTON_SIZE, music_button_pos
from voice_flow.settings import Settings

# Echte Geraeteliste von Bastians PC (15.11.2026).
BASTIAN_PC = [
    (0, "Microsoft Soundmapper - Input"),
    (1, "Kopfhörer (2- Poly VFOCUS2 Seri"),
    (8, "Primärer Soundaufnahmetreiber"),
    (9, "Kopfhörer (2- Poly VFOCUS2 Series)"),
    (22, "Analoger Anschluss (Realtek USB2.0 Audio)"),
    (23, "Line (Realtek USB2.0 Audio)"),
    (24, "Mikrofon (Realtek USB2.0 Audio)"),
    (28, "Mikrofon (NexiGo N60 FHD Webcam Audio)"),
    (35, "Kopfhörer (@System32\drivers\bthhfenum.sys,#2;%1 Hands-Free%0\r\n;(AirPods Pro von Bastian))"),
    (37, "Kopfhörer (@System32\drivers\bthhfenum.sys,#2;%1 Hands-Free%0\r\n;(Poly VFOCUS2 Series))"),
]


def test_settings_musik_default_aus_und_persistiert(tmp_path):
    p = tmp_path / "settings.json"
    s = Settings(p)
    assert s.music_during_recording is False
    s.set_music_during_recording(True)
    assert Settings(p).music_during_recording is True
    s.set_music_during_recording(False)
    assert Settings(p).music_during_recording is False


def test_headset_mikros_erkannt():
    assert is_headset_mic(BASTIAN_PC[9][1])          # Poly Bluetooth Hands-Free
    assert is_headset_mic(BASTIAN_PC[8][1])          # AirPods
    assert is_headset_mic(BASTIAN_PC[3][1])          # Poly ueber USB-Dongle
    assert not is_headset_mic("Mikrofon (NexiGo N60 FHD Webcam Audio)")
    assert not is_headset_mic("Mikrofon (Realtek USB2.0 Audio)")


def test_alternative_ist_webcam():
    assert wired_alternative(BASTIAN_PC) == "Mikrofon (NexiGo N60 FHD Webcam Audio)"


def test_alternative_ohne_webcam_nimmt_realtek():
    ohne = [d for d in BASTIAN_PC if "NexiGo" not in d[1]]
    assert wired_alternative(ohne) == "Mikrofon (Realtek USB2.0 Audio)"


def test_nur_headset_keine_alternative():
    nur = [d for d in BASTIAN_PC if is_headset_mic(d[1])]
    assert wired_alternative(nur) is None


def test_music_safe_device_tauscht_nur_headset(monkeypatch):
    namen = dict(BASTIAN_PC)
    monkeypatch.setattr(audio, "resolve_input_device", lambda c, sr: 37 if "Poly" in str(c) else 24)
    monkeypatch.setattr(audio.sd, "query_devices", lambda i=None: {"name": namen[i]})
    monkeypatch.setattr(audio, "list_input_devices", lambda: BASTIAN_PC)
    assert audio.music_safe_device("Poly VFOCUS2", 16000) == "Mikrofon (NexiGo N60 FHD Webcam Audio)"
    assert audio.music_safe_device("Realtek", 16000) == "Realtek"


def test_knopf_sitzt_links_am_chip():
    chip = (700, 900, 140, 34)
    x, y = music_button_pos(chip)
    assert x + MUSIC_BUTTON_SIZE + MUSIC_BUTTON_GAP == 700
    assert y == 900
