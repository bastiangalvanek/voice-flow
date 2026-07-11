"""Tests: Lang-Audio laeuft als Chunk-Serie durch den Transcriber."""
from __future__ import annotations

import voice_flow.transcription as tr
from voice_flow.transcription import Transcriber


def _transcriber_with_fake_single(monkeypatch, texts: dict[bytes, str]):
    t = Transcriber(api_key="sk-test", model="gpt-4o-mini-transcribe")
    calls: list[bytes] = []

    def fake_single(self, wav_bytes, language="auto", prompt=None):
        calls.append(wav_bytes)
        return texts[wav_bytes]

    monkeypatch.setattr(Transcriber, "_transcribe_single", fake_single)
    return t, calls


def test_single_chunk_uses_original_bytes(monkeypatch):
    wav = b"kurzes-wav"
    monkeypatch.setattr(tr, "split_wav_for_transcription", lambda b: [b])
    t, calls = _transcriber_with_fake_single(monkeypatch, {wav: "hallo"})
    assert t.transcribe(wav, language="de") == "hallo"
    assert calls == [wav]


def test_chunks_are_transcribed_in_order_and_joined(monkeypatch):
    wav = b"langes-wav"
    chunks = [b"c1", b"c2", b"c3"]
    monkeypatch.setattr(tr, "split_wav_for_transcription", lambda b: chunks)
    t, calls = _transcriber_with_fake_single(
        monkeypatch, {b"c1": "erster Teil.", b"c2": "zweiter Teil.", b"c3": "dritter."}
    )
    assert t.transcribe(wav, language="de") == "erster Teil. zweiter Teil. dritter."
    assert calls == chunks


def test_empty_chunk_text_is_skipped_with_gap_warning(monkeypatch, caplog):
    chunks = [b"c1", b"c2"]
    monkeypatch.setattr(tr, "split_wav_for_transcription", lambda b: chunks)
    t, _ = _transcriber_with_fake_single(monkeypatch, {b"c1": "", b"c2": "nur das"})
    with caplog.at_level("WARNING", logger="voice_flow.transcription"):
        assert t.transcribe(b"wav") == "nur das"
    assert any("Luecke" in r.message for r in caplog.records)


def test_empty_bytes_still_raise():
    t = Transcriber(api_key="sk-test")
    try:
        t.transcribe(b"")
        raise AssertionError("ValueError erwartet")
    except ValueError:
        pass
