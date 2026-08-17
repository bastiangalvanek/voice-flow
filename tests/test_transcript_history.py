"""Tests for the persistent transcript history."""
from __future__ import annotations

import json

import pytest

import voice_flow.transcript_history as th


@pytest.fixture
def isolated_history(monkeypatch, tmp_path):
    """Re-point history paths at a tmp dir for every test."""
    monkeypatch.setattr(th, "HISTORY_DIR", tmp_path)
    monkeypatch.setattr(th, "JSONL_FILE", tmp_path / "transcripts.jsonl")
    monkeypatch.setattr(th, "TXT_FILE", tmp_path / "transcripts.txt")
    return tmp_path


def test_append_writes_jsonl_entry(isolated_history):
    th.append_transcript(
        text="hello world",
        duration_sec=1.5,
        word_count=2,
        model="whisper-1",
        pipeline_ms=850,
    )
    jsonl = th.JSONL_FILE.read_text(encoding="utf-8")
    entry = json.loads(jsonl.strip())
    assert entry["text"] == "hello world"
    assert entry["duration_sec"] == 1.5
    assert entry["word_count"] == 2
    assert entry["model"] == "whisper-1"
    assert entry["pipeline_ms"] == 850
    assert "timestamp" in entry


def test_append_writes_human_readable_txt(isolated_history):
    th.append_transcript(text="quick check", duration_sec=0.8, word_count=2)
    txt = th.TXT_FILE.read_text(encoding="utf-8")
    assert "quick check" in txt
    assert "2 Woerter" in txt   # 18.08: Ausgabe ist deutsch, nicht englisch
    assert "==========" in txt  # day header


def test_append_pluralizes_word_singular(isolated_history):
    th.append_transcript(text="hi", word_count=1)
    txt = th.TXT_FILE.read_text(encoding="utf-8")
    assert "1 Wort" in txt      # 18.08: Ausgabe ist deutsch, nicht englisch
    assert "1 words" not in txt


def test_append_skips_empty_text(isolated_history):
    th.append_transcript(text="")
    th.append_transcript(text="   \n\t  ")
    assert not th.JSONL_FILE.exists()
    assert not th.TXT_FILE.exists()


def test_append_multiple_entries_same_day_one_header(isolated_history):
    th.append_transcript(text="first", word_count=1)
    th.append_transcript(text="second", word_count=1)
    txt = th.TXT_FILE.read_text(encoding="utf-8")
    # Both entries present, only one day header
    assert txt.count("==========") == 2  # opening and closing of one header
    assert "first" in txt
    assert "second" in txt


def test_get_history_paths_returns_all_three(isolated_history):
    paths = th.get_history_paths()
    assert paths["jsonl"] == th.JSONL_FILE
    assert paths["txt"] == th.TXT_FILE
    assert paths["dir"] == th.HISTORY_DIR


def test_append_creates_dir_if_missing(monkeypatch, tmp_path):
    nested = tmp_path / "deep" / "nest"
    monkeypatch.setattr(th, "HISTORY_DIR", nested)
    monkeypatch.setattr(th, "JSONL_FILE", nested / "transcripts.jsonl")
    monkeypatch.setattr(th, "TXT_FILE", nested / "transcripts.txt")
    th.append_transcript(text="hi", word_count=1)
    assert nested.exists()
    assert th.JSONL_FILE.exists()


def test_append_jsonl_is_one_line_per_entry(isolated_history):
    th.append_transcript(text="a", word_count=1)
    th.append_transcript(text="b", word_count=1)
    lines = th.JSONL_FILE.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    for line in lines:
        json.loads(line)  # each line is valid JSON


def test_append_preserves_unicode(isolated_history):
    th.append_transcript(text="héllo wörld — 한국어", word_count=3)
    jsonl = th.JSONL_FILE.read_text(encoding="utf-8")
    entry = json.loads(jsonl.strip())
    assert entry["text"] == "héllo wörld — 한국어"
    txt = th.TXT_FILE.read_text(encoding="utf-8")
    assert "héllo wörld — 한국어" in txt
