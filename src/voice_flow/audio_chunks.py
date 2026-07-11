"""Lang-Audio-Split fuer die Transcription-API: WAV an Stille-Grenzen zerlegen.

Warum (11.07 Bastian, 14.5-Min-Diktat verloren gegangen): Die Pipeline prüfte
das 25-MB-Limit auf den ROHEN WAV-Bytes und brach ab, bevor die Opus-
Kompression überhaupt lief (27 MB WAV wären ~2.4 MB Opus gewesen). Statt den
Check zu verschieben, eliminiert dieses Modul die Fehlerklasse "zu lang"
komplett: Aufnahmen über CHUNK_TRIGGER_SEC werden in ~5-Minuten-Stücke
geschnitten und einzeln transkribiert. Geschnitten wird nicht stur bei 300s,
sondern an der LEISESTEN Stelle in einem Suchfenster um den Ziel-Schnitt —
sonst zerteilt der Schnitt ein Wort und beide Chunk-Transkripte kleben Müll
an die Naht.

Bewusst nur Stdlib `wave` + numpy (numpy ist über sounddevice ohnehin da):
kein soundfile nötig, der Split funktioniert auch wenn Opus-Encoding fehlt.
Kurze Aufnahmen (<= CHUNK_TRIGGER_SEC) gehen als identische Bytes zurück —
der bewährte Single-Call-Pfad bleibt byte-gleich unangetastet.
"""
from __future__ import annotations

import io
import logging
import wave

import numpy as np

log = logging.getLogger(__name__)

# 5-Minuten-Chunks: ~10 MB WAV / ~0.5 MB Opus, ~700 Worte Deutsch — komfortabel
# unter jedem API-Limit (Upload-Größe UND Output-Token-Truncation bei den
# gpt-4o-Transcribe-Modellen).
CHUNK_TARGET_SEC = 300.0
# Erst ab hier wird gesplittet: target + Puffer, damit eine 5:10-Aufnahme nicht
# in 5:00 + 10s-Krümel zerfällt.
CHUNK_TRIGGER_SEC = 330.0
# Suchfenster um den Ziel-Schnitt, in dem die leiseste Stelle gesucht wird.
SILENCE_SEARCH_SEC = 20.0
# Breite des RMS-Fensters, das als potenzielle Schnitt-Stille bewertet wird.
SILENCE_WIN_SEC = 0.4
# Ein Rest kürzer als das wird an den vorherigen Chunk gehängt statt ein
# Mini-Chunk zu werden (Whisper halluziniert auf Sekunden-Schnipseln gern).
MIN_TAIL_SEC = 30.0


def wav_duration_seconds(wav_bytes: bytes) -> float:
    """Dauer eines WAV in Sekunden. 0.0 bei kaputtem/leerem Input."""
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            rate = wf.getframerate()
            return wf.getnframes() / rate if rate else 0.0
    except Exception:  # noqa: BLE001 - Aufrufer behandeln 0.0 als "unbekannt"
        return 0.0


def split_wav_for_transcription(wav_bytes: bytes) -> list[bytes]:
    """WAV in transkriptions-taugliche Chunks schneiden.

    <= CHUNK_TRIGGER_SEC → [wav_bytes] unverändert (Identität, kein Re-Encode).
    Sonst: Schnitte an den leisesten Stellen nahe der 300s-Raster, jeder Chunk
    ein vollständiges, eigenständiges WAV mit identischen Audio-Parametern.
    Bei nicht parsebarem WAV: [wav_bytes] (der API-Call soll den Fehler zeigen,
    nicht der Splitter ihn verschlucken).
    """
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            nchannels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            nframes = wf.getnframes()
            raw = wf.readframes(nframes)
    except Exception as ex:  # noqa: BLE001 - kaputtes WAV geht unzerteilt zum API-Call
        log.warning("Chunk-Split: WAV nicht lesbar (%s) — sende ungeteilt.", ex)
        return [wav_bytes]

    if not framerate or not nframes:
        return [wav_bytes]
    duration = nframes / framerate
    if duration <= CHUNK_TRIGGER_SEC:
        return [wav_bytes]

    cut_frames = _plan_cuts(raw, nchannels, sampwidth, framerate, nframes)
    frame_bytes = nchannels * sampwidth
    chunks: list[bytes] = []
    bounds = [0, *cut_frames, nframes]
    pairs = list(zip(bounds, bounds[1:], strict=False))
    for start, end in pairs:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as out:
            out.setnchannels(nchannels)
            out.setsampwidth(sampwidth)
            out.setframerate(framerate)
            out.writeframes(raw[start * frame_bytes : end * frame_bytes])
        chunks.append(buf.getvalue())
    log.info(
        "LANG-AUDIO  %.1f min → %d Chunks (%s).",
        duration / 60.0,
        len(chunks),
        ", ".join(f"{(e - s) / framerate:.0f}s" for s, e in pairs),
    )
    return chunks


def _plan_cuts(
    raw: bytes, nchannels: int, sampwidth: int, framerate: int, nframes: int
) -> list[int]:
    """Schnitt-Frames bestimmen: 300s-Raster, verschoben auf die leiseste Stelle.

    Nur 16-bit-PCM bekommt die Stille-Suche (unser Recorder schreibt nichts
    anderes); exotische Sample-Breiten schneiden stur am Raster — immer noch
    besser als gar nicht transkribieren.
    """
    target = int(CHUNK_TARGET_SEC * framerate)
    search = int(SILENCE_SEARCH_SEC * framerate)
    min_tail = int(MIN_TAIL_SEC * framerate)

    energy: np.ndarray | None = None
    if sampwidth == 2:
        samples = np.frombuffer(raw, dtype=np.int16)
        if nchannels > 1:
            samples = samples.reshape(-1, nchannels).mean(axis=1)
        energy = samples.astype(np.float64) ** 2

    cuts: list[int] = []
    start = 0
    while nframes - start > target + min_tail:
        ideal = start + target
        lo = max(start + min_tail, ideal - search)
        hi = min(nframes - min_tail, ideal + search)
        cut = _quietest_frame(energy, lo, hi, framerate) if energy is not None else ideal
        cuts.append(int(cut))
        start = int(cut)
    return cuts


def _quietest_frame(energy: np.ndarray, lo: int, hi: int, framerate: int) -> int:
    """Mitte des energie-ärmsten SILENCE_WIN_SEC-Fensters in [lo, hi]."""
    win = max(1, int(SILENCE_WIN_SEC * framerate))
    if hi - lo <= win:
        return (lo + hi) // 2
    region = energy[lo:hi]
    # Gleitende Fenster-Summe über cumsum: O(n), kein Python-Loop.
    csum = np.concatenate(([0.0], np.cumsum(region)))
    window_sums = csum[win:] - csum[:-win]
    return lo + int(np.argmin(window_sums)) + win // 2
