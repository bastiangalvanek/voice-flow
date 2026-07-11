"""Tests fuer Immer-Archiv (Opus) + Retention (Alter + Groessen-Deckel)."""
from __future__ import annotations

import io
import os
import time
import wave

import numpy as np
import pytest

import voice_flow.audio_encode as audio_encode
import voice_flow.recording_storage as rs


def _tiny_wav(duration_sec: float = 0.5) -> bytes:
    n = int(duration_sec * 16000)
    samples = np.zeros(n, dtype=np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


@pytest.fixture
def recordings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "RECORDINGS_DIR", tmp_path)
    return tmp_path


def _age(path, days: float) -> None:
    old = time.time() - days * 86400
    os.utime(path, (old, old))


def test_archive_creates_ogg_and_removes_wav(recordings_dir):
    wav_path = recordings_dir / "recording_x.wav"
    wav_path.write_bytes(_tiny_wav())
    result = rs.archive_recording(wav_path)
    assert result is not None
    assert result.suffix == ".ogg"
    assert result.exists()
    assert not wav_path.exists()


def test_archive_marks_wav_archived_when_encoding_fails(recordings_dir, monkeypatch):
    monkeypatch.setattr(audio_encode, "to_opus", lambda _b: None)
    wav_path = recordings_dir / "recording_y.wav"
    wav_path.write_bytes(_tiny_wav())
    result = rs.archive_recording(wav_path)
    # Audio nie verlieren, aber als erledigt markieren (kein Pending-Fehlalarm):
    assert result == recordings_dir / "recording_y_archived.wav"
    assert result.exists()
    assert not wav_path.exists()


def test_archive_missing_file_returns_none(recordings_dir):
    assert rs.archive_recording(recordings_dir / "recording_weg.wav") is None


def test_cleanup_age_covers_done_files_only(recordings_dir):
    old_recovered = recordings_dir / "recording_old_recovered.wav"
    old_ogg = recordings_dir / "recording_old2.ogg"
    old_txt = recordings_dir / "recording_old2.txt"
    fresh = recordings_dir / "recording_fresh.ogg"
    for f in (old_recovered, old_ogg, old_txt, fresh):
        f.write_bytes(b"x" * 10)
    for f in (old_recovered, old_ogg, old_txt):
        _age(f, rs.RETENTION_DAYS + 5)

    deleted = rs.cleanup_old_recordings()
    assert deleted == 3
    assert fresh.exists()
    assert not old_recovered.exists() and not old_ogg.exists() and not old_txt.exists()


def test_cleanup_never_touches_open_work(recordings_dir):
    """Critic P1: un-recovertes Audio ist fuer Alter UND Deckel TABU."""
    failed = recordings_dir / "recording_f_failed.wav"
    suspect = recordings_dir / "recording_s_suspect.wav"
    plain = recordings_dir / "recording_p.wav"
    for f in (failed, suspect, plain):
        f.write_bytes(b"x" * 1000)
        _age(f, rs.RETENTION_DAYS + 100)

    deleted = rs.cleanup_old_recordings(max_total_bytes=10)
    assert deleted == 0
    assert failed.exists() and suspect.exists() and plain.exists()


def test_cleanup_size_cap_drops_oldest_first(recordings_dir):
    oldest = recordings_dir / "recording_a_recovered.wav"
    middle = recordings_dir / "recording_b_recovered.wav"
    newest = recordings_dir / "recording_c_recovered.wav"
    for f in (oldest, middle, newest):
        f.write_bytes(b"x" * 100)
    _age(oldest, 3)
    _age(middle, 2)
    _age(newest, 1)

    deleted = rs.cleanup_old_recordings(max_total_bytes=250)
    assert deleted == 1
    assert not oldest.exists()
    assert middle.exists() and newest.exists()


def test_list_pending_is_exactly_open_work(recordings_dir):
    (recordings_dir / "recording_1_failed.wav").write_bytes(b"x")
    (recordings_dir / "recording_2_suspect.wav").write_bytes(b"x")
    (recordings_dir / "recording_3_recovered.wav").write_bytes(b"x")
    (recordings_dir / "recording_4.ogg").write_bytes(b"x")
    (recordings_dir / "recording_5_archived.wav").write_bytes(b"x")
    (recordings_dir / "recording_6.wav").write_bytes(b"x")  # plain = Crash-Rest
    names = [p.name for p in rs.list_pending_recordings()]
    assert names == [
        "recording_1_failed.wav",
        "recording_2_suspect.wav",
        "recording_6.wav",
    ]


def test_mark_recovered_handles_all_suffixes(recordings_dir):
    from voice_flow.recover import mark_recovered

    for name, expected in [
        ("recording_1_failed.wav", "recording_1_recovered.wav"),
        ("recording_2_suspect.wav", "recording_2_recovered.wav"),
        ("recording_3.wav", "recording_3_recovered.wav"),
    ]:
        p = recordings_dir / name
        p.write_bytes(b"x")
        assert mark_recovered(p).name == expected
