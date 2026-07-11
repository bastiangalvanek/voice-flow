"""Tests fuer den Lang-Audio-Split (audio_chunks).

Synthetisches WAV mit bekannten Stille-Fenstern; niedrige Sample-Rate haelt
die Arrays klein (die Konstanten skalieren in Sekunden, nicht Frames).
"""
from __future__ import annotations

import io
import wave

import numpy as np

from voice_flow.audio_chunks import (
    CHUNK_TARGET_SEC,
    CHUNK_TRIGGER_SEC,
    MIN_TAIL_SEC,
    SILENCE_SEARCH_SEC,
    split_wav_for_transcription,
    wav_duration_seconds,
)

RATE = 1000  # 1 kHz reicht: Splitter rechnet in Sekunden x Framerate


def _make_wav(duration_sec: float, silence_at: list[float] | None = None) -> bytes:
    """Laut-Rauschen mit 1s-Stille-Fenstern an den gegebenen Positionen."""
    n = int(duration_sec * RATE)
    rng = np.random.default_rng(42)
    samples = (rng.integers(-20000, 20000, n)).astype(np.int16)
    for pos in silence_at or []:
        i = int(pos * RATE)
        samples[i : i + RATE] = 0
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


def _frames(wav_bytes: bytes) -> int:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        return wf.getnframes()


def test_short_audio_is_identity():
    wav = _make_wav(CHUNK_TRIGGER_SEC - 1)
    chunks = split_wav_for_transcription(wav)
    assert chunks == [wav]  # byte-identisch, alter Single-Call-Pfad unangetastet


def test_long_audio_splits_at_silence():
    # 700s mit Stille bei 290s und 590s — nahe der 300er-Raster.
    wav = _make_wav(700, silence_at=[290, 590])
    chunks = split_wav_for_transcription(wav)
    assert len(chunks) == 3
    # Kein Sample verloren oder doppelt:
    assert sum(_frames(c) for c in chunks) == _frames(wav)
    # Schnitte liegen IN den Stille-Fenstern (290-291s bzw. dann relativ):
    first = _frames(chunks[0]) / RATE
    assert 290 <= first <= 291
    second_abs = first + _frames(chunks[1]) / RATE
    assert 590 <= second_abs <= 591


def test_long_audio_without_silence_cuts_near_target():
    wav = _make_wav(620)  # kein Stille-Fenster -> Schnitt im Suchfenster ums Raster
    chunks = split_wav_for_transcription(wav)
    assert len(chunks) == 2
    first = _frames(chunks[0]) / RATE
    assert abs(first - CHUNK_TARGET_SEC) <= SILENCE_SEARCH_SEC + 1
    # Jeder Chunk ist ein gueltiges, lesbares WAV mit den Original-Parametern:
    for c in chunks:
        with wave.open(io.BytesIO(c), "rb") as wf:
            assert wf.getframerate() == RATE
            assert wf.getnchannels() == 1


def test_no_tiny_tail_chunk():
    # 310s: ueber target, aber Rest unter MIN_TAIL -> ungeteilt lassen wenn
    # unter Trigger; 340s -> geteilt, aber der Tail muss >= MIN_TAIL sein.
    wav = _make_wav(CHUNK_TRIGGER_SEC + 10)
    chunks = split_wav_for_transcription(wav)
    assert all(_frames(c) / RATE >= MIN_TAIL_SEC for c in chunks)


def test_broken_wav_passes_through():
    garbage = b"definitiv kein wav"
    assert split_wav_for_transcription(garbage) == [garbage]
    assert wav_duration_seconds(garbage) == 0.0


def test_duration_helper():
    wav = _make_wav(12.5)
    assert abs(wav_duration_seconds(wav) - 12.5) < 0.01
