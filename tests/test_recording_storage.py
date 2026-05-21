"""Tests for the on-disk recording backup helpers."""
from __future__ import annotations

import time

import pytest

import voice_flow.recording_storage as rs


@pytest.fixture
def isolated_recordings_dir(monkeypatch, tmp_path):
    """Point RECORDINGS_DIR at a fresh tmp_path for every test."""
    monkeypatch.setattr(rs, "RECORDINGS_DIR", tmp_path)
    return tmp_path


def test_save_recording_writes_file_with_wav_extension(isolated_recordings_dir):
    path = rs.save_recording(b"RIFFsome-wav-bytes")
    assert path.exists()
    assert path.suffix == ".wav"
    assert path.parent == isolated_recordings_dir
    assert path.read_bytes() == b"RIFFsome-wav-bytes"


def test_save_recording_with_suffix(isolated_recordings_dir):
    path = rs.save_recording(b"x", suffix="_test")
    assert path.stem.endswith("_test")


def test_save_recording_creates_dir_if_missing(monkeypatch, tmp_path):
    target = tmp_path / "deep" / "nested" / "recordings"
    monkeypatch.setattr(rs, "RECORDINGS_DIR", target)
    path = rs.save_recording(b"x")
    assert path.parent == target
    assert path.exists()


def test_delete_recording_removes_file(isolated_recordings_dir):
    path = rs.save_recording(b"x")
    assert path.exists()
    rs.delete_recording(path)
    assert not path.exists()


def test_delete_recording_handles_missing_file(isolated_recordings_dir):
    # Must not raise — file already gone
    rs.delete_recording(isolated_recordings_dir / "nonexistent.wav")


def test_delete_recording_handles_none():
    rs.delete_recording(None)  # must not raise


def test_mark_failed_renames_with_suffix(isolated_recordings_dir):
    path = rs.save_recording(b"x")
    failed = rs.mark_failed(path)
    assert failed.exists()
    assert failed.stem.endswith("_failed")
    assert not path.exists()


def test_mark_failed_returns_original_on_missing(isolated_recordings_dir):
    missing = isolated_recordings_dir / "nope.wav"
    result = rs.mark_failed(missing)
    assert result == missing  # untouched


def test_mark_failed_handles_none():
    assert rs.mark_failed(None) is None


def test_cleanup_old_recordings_removes_older_than_retention(
    isolated_recordings_dir, monkeypatch
):
    fresh = rs.save_recording(b"new")
    # 2 ms is enough to push the next save's timestamp into a fresh filename.
    # In production this is not an issue: min_recording_sec is 0.3 s.
    time.sleep(0.002)
    old = rs.save_recording(b"old")
    assert fresh != old, "filenames must differ — increase the sleep above if this flakes"

    # Backdate `old` by 30 days
    backdate = time.time() - 30 * 86400
    import os
    os.utime(old, (backdate, backdate))

    count = rs.cleanup_old_recordings(max_age_days=7)
    assert count == 1
    assert fresh.exists()
    assert not old.exists()


def test_cleanup_old_recordings_returns_zero_when_dir_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(rs, "RECORDINGS_DIR", tmp_path / "does-not-exist")
    assert rs.cleanup_old_recordings() == 0


def test_list_pending_recordings_returns_all_wavs(isolated_recordings_dir):
    rs.save_recording(b"a")
    rs.save_recording(b"b", suffix="_failed")
    pending = rs.list_pending_recordings()
    assert len(pending) == 2
    # sorted, both .wav
    assert all(p.suffix == ".wav" for p in pending)


def test_list_pending_recordings_empty_when_dir_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(rs, "RECORDINGS_DIR", tmp_path / "missing")
    assert rs.list_pending_recordings() == []


# ── check_size_for_whisper ────────────────────────────────────────────


def test_check_size_for_whisper_ok_small():
    ok, msg = rs.check_size_for_whisper(b"x" * 1024)
    assert ok is True
    assert msg == ""


def test_check_size_for_whisper_warns_near_limit():
    near_limit = b"x" * (23 * 1024 * 1024)  # 23 MB
    ok, msg = rs.check_size_for_whisper(near_limit)
    assert ok is True
    assert "close to the 25 MB limit" in msg


def test_check_size_for_whisper_rejects_over_limit():
    over = b"x" * (26 * 1024 * 1024)
    ok, msg = rs.check_size_for_whisper(over)
    assert ok is False
    assert "exceeds Whisper limit" in msg


def test_save_recording_makes_unique_filenames(isolated_recordings_dir):
    """Filenames are timestamped to ms precision — saves in different ms slots differ."""
    p1 = rs.save_recording(b"a")
    time.sleep(0.002)  # cross at least one ms tick
    p2 = rs.save_recording(b"b")
    assert p1 != p2
    assert p1.exists() and p2.exists()
