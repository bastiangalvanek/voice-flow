"""Tests: verwaisten Screenshot-Bucket einer Aufnahme zuordnen + Offsets ableiten."""
from __future__ import annotations

import os
from datetime import datetime

from PIL import Image

from voice_flow.session_link import (
    derive_captures,
    find_session_for,
    parse_recording_stop,
    parse_session_start,
)


def _png(path, mtime: float | None = None) -> None:
    Image.new("RGB", (4, 4), (10, 20, 30)).save(path)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def test_parse_session_start():
    from pathlib import Path

    assert parse_session_start(Path("2026-07-11_16-55-16")) == datetime(2026, 7, 11, 16, 55, 16)
    assert parse_session_start(Path("nonsense")) is None


def test_parse_recording_stop():
    from pathlib import Path

    assert parse_recording_stop(
        Path("recording_20260711_170948_502_failed.wav")
    ) == datetime(2026, 7, 11, 17, 9, 48)
    assert parse_recording_stop(Path("foo.wav")) is None


def test_find_session_matches_by_start_minus_duration(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    bucket = sessions / "2026-07-11_16-55-16"
    bucket.mkdir()
    _png(bucket / "shot_01.png")

    rec = tmp_path / "recording_20260711_170948_502_failed.wav"
    rec.write_bytes(b"x")
    # Stop 17:09:48, Dauer 872s → erwarteter Start 16:55:16 = Bucket.
    found = find_session_for(rec, duration=872.0, sessions_dir=sessions)
    assert found == bucket


def test_find_session_rejects_out_of_tolerance(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    bucket = sessions / "2026-07-11_10-00-00"
    bucket.mkdir()
    _png(bucket / "shot_01.png")
    rec = tmp_path / "recording_20260711_170948_502.wav"
    rec.write_bytes(b"x")
    assert find_session_for(rec, duration=100.0, sessions_dir=sessions) is None


def test_find_session_skips_empty_bucket(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "2026-07-11_16-55-16").mkdir()  # keine Shots
    rec = tmp_path / "recording_20260711_170948_502.wav"
    rec.write_bytes(b"x")
    assert find_session_for(rec, duration=872.0, sessions_dir=sessions) is None


def test_derive_captures_offsets_and_order(tmp_path):
    bucket = tmp_path / "2026-07-11_16-55-16"
    bucket.mkdir()
    start = datetime(2026, 7, 11, 16, 55, 16).timestamp()
    _png(bucket / "shot_01.png", mtime=start + 63)
    _png(bucket / "shot_02.png", mtime=start + 560)
    _png(bucket / "shot_03.png", mtime=start + 717)

    caps = derive_captures(bucket, "N{n}:{name}:{path}")
    offsets = [round(o) for o, _ in caps]
    assert offsets == [63, 560, 717]
    assert caps[0][1].startswith("N1:shot_01.png:")
    assert str(bucket) in caps[0][1]  # absoluter Pfad im Marker


def test_derive_captures_clamps_negative_offset(tmp_path):
    bucket = tmp_path / "2026-07-11_16-55-16"
    bucket.mkdir()
    start = datetime(2026, 7, 11, 16, 55, 16).timestamp()
    _png(bucket / "shot_01.png", mtime=start - 30)  # vor Start (Uhr-Schräglage)
    caps = derive_captures(bucket, "{n}")
    assert caps[0][0] == 0.0
