"""Rettungsnetz gegen den CoreAudio-Deadlock vom 16.08.2026.

Damals hing `AudioRecorder.stop()` unaufloesbar in PortAudio/CoreAudio (Mikro-Wechsel
waehrend der Aufnahme). 2m54s Diktat lagen NUR im RAM des eingefrorenen Prozesses.

Diese Tests decken die beiden Schutzschichten ab:
  1. Live-Spool  — die laufende Aufnahme steht schon waehrend des Sprechens auf Platte
                   und ist zu JEDEM Zeitpunkt eine gueltige WAV (Absturz/kill -9).
  2. Stop-Timeout — ein haengendes close() blockiert nicht mehr ewig; die Aufnahme
                   wird ausgeliefert und die Mitschrift als Rettungsdatei behalten.
"""
from __future__ import annotations

import os
import sys
import threading
import types
import wave

import numpy as np
import pytest


class _FakeStream:
    def __init__(self, **kwargs):
        self.callback = kwargs.get("callback")
        self.closed = False

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        self.closed = True


class _HangingStream(_FakeStream):
    """Simuliert exakt den CoreAudio-Deadlock: stop() kehrt nie zurueck."""

    def stop(self):
        threading.Event().wait()  # blockt fuer immer


@pytest.fixture
def fake_sd(monkeypatch):
    import voice_flow.audio as audio_mod

    fake = types.ModuleType("sounddevice")
    fake.InputStream = _FakeStream  # type: ignore[attr-defined]
    fake.query_devices = lambda *a: ""  # type: ignore[attr-defined]
    fake.default = types.SimpleNamespace(device=[0, 1])  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    monkeypatch.setattr(audio_mod, "sd", fake)
    yield fake


def _feed(recorder, blocks: int = 4, samples: int = 800) -> None:
    frame = np.full((samples, 1), 1234, dtype=np.int16)
    for _ in range(blocks):
        recorder._callback(frame, samples, None, None)


# ---------- Schicht 1: Live-Spool ----------


def test_spool_datei_ist_waehrend_der_aufnahme_schon_lesbar(fake_sd, tmp_path):
    """Der Kern: mitten in der Aufnahme liegt bereits gueltiges Audio auf Platte."""
    from voice_flow.audio import AudioRecorder

    r = AudioRecorder(spool_dir=tmp_path)
    r.start()
    _feed(r, blocks=4, samples=800)

    # Flush erzwingen wie der Spool-Thread es tut (ohne 3s zu warten).
    r._spool.write(np.concatenate(list(r._frames), axis=0).tobytes())

    partials = list(tmp_path.glob("recording_*_partial.wav"))
    assert len(partials) == 1, "Mitschrift muss waehrend der Aufnahme existieren"

    # Ohne close() lesbar? Genau das entscheidet nach einem kill -9.
    with wave.open(str(partials[0]), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 16000
        assert wf.getnframes() == 3200  # 4 x 800 Samples
        assert np.frombuffer(wf.readframes(3200), dtype=np.int16)[0] == 1234

    r.stop()


def test_spool_wird_bei_sauberem_stop_wieder_entfernt(fake_sd, tmp_path):
    """Normalbetrieb: kein Datei-Muell, die vollstaendige WAV kommt aus dem RAM."""
    from voice_flow.audio import AudioRecorder

    r = AudioRecorder(spool_dir=tmp_path)
    r.start()
    _feed(r)
    wav = r.stop()

    assert wav[:4] == b"RIFF"
    assert list(tmp_path.glob("*_partial.wav")) == []


def test_ohne_spool_dir_wird_nichts_geschrieben(fake_sd, tmp_path):
    """Bibliotheks-/Test-Nutzung ohne Spool bleibt unveraendert."""
    from voice_flow.audio import AudioRecorder

    r = AudioRecorder()
    r.start()
    _feed(r)
    r.stop()

    assert r._spool is None
    assert list(tmp_path.iterdir()) == []


# ---------- Schicht 2: Stop-Timeout ----------


def test_haengender_stop_liefert_audio_statt_einzufrieren(fake_sd, tmp_path, monkeypatch):
    """Der Vorfall selbst: CoreAudio haengt — stop() muss trotzdem zurueckkehren."""
    import voice_flow.audio as audio_mod
    from voice_flow.audio import AudioRecorder

    fake_sd.InputStream = _HangingStream
    monkeypatch.setattr(audio_mod, "STOP_TIMEOUT_SEC", 0.3)

    r = AudioRecorder(spool_dir=tmp_path)
    r.start()
    _feed(r, blocks=5, samples=1600)

    wav = r.stop()  # frueher: haengt fuer immer

    assert wav[:4] == b"RIFF"
    assert r.audio_system_stuck is True
    assert r.duration_seconds == pytest.approx(0.5, abs=0.01)


def test_haengender_stop_behaelt_die_rettungsdatei(fake_sd, tmp_path, monkeypatch):
    """Bei einem Haenger ist die Mitschrift die einzige Kopie — sie muss bleiben."""
    import voice_flow.audio as audio_mod
    from voice_flow.audio import AudioRecorder

    fake_sd.InputStream = _HangingStream
    monkeypatch.setattr(audio_mod, "STOP_TIMEOUT_SEC", 0.3)

    r = AudioRecorder(spool_dir=tmp_path)
    r.start()
    _feed(r, blocks=4, samples=800)
    r.stop()

    partials = list(tmp_path.glob("recording_*_partial.wav"))
    assert len(partials) == 1, "Rettungsdatei darf bei einem Haenger NIE geloescht werden"
    with wave.open(str(partials[0]), "rb") as wf:
        assert wf.getnframes() == 3200


def test_rettungsdatei_ist_fuer_retention_und_recover_sichtbar(tmp_path, monkeypatch):
    """Die _partial-Datei muss die Aufraeum-Automatik ueberleben und auffindbar sein."""
    import voice_flow.recording_storage as rs

    monkeypatch.setattr(rs, "RECORDINGS_DIR", tmp_path)
    partial = tmp_path / "recording_20260816_224237_000_partial.wav"
    partial.write_bytes(b"RIFF____WAVEfake")
    old = os.stat(partial).st_atime
    os.utime(partial, (old, old - 400 * 86400))  # kuenstlich uralt

    assert rs.cleanup_old_recordings(max_age_days=1, max_total_bytes=1) == 0
    assert partial.exists(), "Retention darf offene Rettungsdateien nie loeschen"
    assert partial in rs.list_pending_recordings()


def test_nach_haenger_friert_der_naechste_start_nicht_ein(fake_sd, tmp_path, monkeypatch):
    """Ein zweiter Versuch wuerde im selben OS-Mutex haengen — diesmal ohne Rettung."""
    import voice_flow.audio as audio_mod
    from voice_flow.audio import AudioRecorder

    fake_sd.InputStream = _HangingStream
    monkeypatch.setattr(audio_mod, "STOP_TIMEOUT_SEC", 0.3)

    r = AudioRecorder(spool_dir=tmp_path)
    r.start()
    _feed(r)
    r.stop()

    with pytest.raises(RuntimeError, match="haengt"):
        r.start()


def test_letzter_flush_nach_close_wirft_nicht(tmp_path):
    """Race: Spool-Thread schreibt, waehrend stop() die Datei schon schliesst."""
    from voice_flow.spool import WavSpool

    spool = WavSpool(tmp_path / "x_partial.wav")
    spool.open()
    spool.write(b"\x01\x02" * 10)
    spool.close()
    spool.write(b"\x03\x04" * 10)  # darf NICHT werfen

    with wave.open(str(tmp_path / "x_partial.wav"), "rb") as wf:
        assert wf.getnframes() == 10


# ---------- Verdrahtung: der Schutz darf nicht still verloren gehen ----------


def test_app_erzeugt_recorder_mit_spool(monkeypatch):
    """Ohne spool_dir waere der ganze Schutz in Produktion wirkungslos."""
    import inspect

    import voice_flow.app as app_mod

    src = inspect.getsource(app_mod.VoiceFlowApp.__init__)
    assert "spool_dir=RECORDINGS_DIR" in src
