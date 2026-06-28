import io
import wave

import numpy as np

from voice_flow import audio_encode


def _wav(seconds: float, sr: int = 16000) -> bytes:
    n = int(seconds * sr)
    # leiser Sinus -> realistischer als Stille, gut komprimierbar
    t = np.linspace(0, seconds, n, endpoint=False)
    samples = (np.sin(2 * np.pi * 220 * t) * 8000).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


def test_to_opus_shrinks_and_is_decodable():
    wav = _wav(2.0)
    opus = audio_encode.to_opus(wav)
    assert opus is not None
    assert len(opus) < len(wav)  # muss kleiner sein, sonst kein Gewinn
    # zurueck-dekodierbar (gueltiger OGG/Opus-Stream)?
    import soundfile as sf

    data, sr = sf.read(io.BytesIO(opus))
    assert sr == 16000
    assert len(data) > 0


def test_to_opus_empty_returns_none():
    assert audio_encode.to_opus(b"") is None


def test_to_opus_garbage_returns_none():
    # Kein gueltiges WAV -> sauberer Fallback (None), kein Crash.
    assert audio_encode.to_opus(b"not a wav file at all") is None


def test_to_opus_unsupported_samplerate_returns_none():
    # 44100 ist keine Opus-Eingangs-Rate -> None (Aufrufer sendet WAV).
    assert audio_encode.to_opus(_wav(1.0, sr=44100)) is None
