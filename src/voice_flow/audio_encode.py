"""WAV -> OGG/Opus Kompression fuer den Upload zur OpenAI-Transcription-API.

Warum (28.06 Bastian "schneller"): Die API bekam bisher unkomprimiertes PCM-WAV
(16 kHz mono = ~1.9 MB/Minute). Gemessen an 27.5s echtem Sprach-Audio:
  WAV  860 KB -> 3.0s   |   OGG/Opus  89 KB -> 1.3s   (2.3x schneller, gleiche
72-Wort-Transkription). Die Latenz ist upload-bound, nicht compute-bound ->
Kompression ist der Hebel. Opus ist fuer Sprache verlustfrei genug (Whisper-
Ergebnis identisch) und ~10x kleiner.

Bewusst defensiv: schlaegt das Encoding fehl (libsndfile ohne Opus, exotische
Sample-Rate, kaputtes WAV), gibt to_opus() None zurueck -> der Aufrufer sendet
das Original-WAV. Nie haerter scheitern als der Status quo.
"""
from __future__ import annotations

import io
import logging

log = logging.getLogger(__name__)

# OGG/Opus unterstuetzt nur diese Eingangs-Sample-Rates (libopus). Die App nimmt
# mit 16000 auf; alles andere faellt sauber auf WAV zurueck.
_OPUS_RATES = frozenset({8000, 12000, 16000, 24000, 48000})


def to_opus(wav_bytes: bytes) -> bytes | None:
    """WAV-Bytes -> OGG/Opus-Bytes. None bei jeder Art von Fehler (Fallback=WAV)."""
    if not wav_bytes:
        return None
    try:
        import soundfile as sf  # lazy: fehlt die lib, faellt der Aufrufer auf WAV

        data, samplerate = sf.read(io.BytesIO(wav_bytes), dtype="int16")
        if samplerate not in _OPUS_RATES:
            log.debug("Opus skip: Sample-Rate %d nicht Opus-tauglich.", samplerate)
            return None
        out = io.BytesIO()
        sf.write(out, data, samplerate, format="OGG", subtype="OPUS")
        opus = out.getvalue()
        # Sanity: nur nutzen wenn es wirklich kleiner ist (sonst kein Gewinn).
        if not opus or len(opus) >= len(wav_bytes):
            return None
        return opus
    except Exception as ex:  # noqa: BLE001 - Kompression ist optional, nie hart scheitern
        log.debug("Opus-Encoding fehlgeschlagen (%s) — sende WAV.", ex)
        return None
