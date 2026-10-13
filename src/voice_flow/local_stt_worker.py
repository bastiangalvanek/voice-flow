"""Lokale Spracherkennung als eigener Prozess (laeuft in .venv-lokal, NICHT in .venv).

13.10.2026 Bastian: OpenAI-Guthaben leer, zwei Diktate verloren — "bau ein, mit
Wortliste und Grafikkarte". faster-whisper + CUDA brauchen Python <= 3.12 und
~600 MB Grafik-Bibliotheken; die taegliche Diktier-venv (Python 3.14) bleibt
deshalb unangetastet und spricht mit diesem Prozess ueber stdin/stdout.

Bewusst ohne Import aus voice_flow: das Paket ist in .venv-lokal nicht installiert.

Protokoll (je eine JSON-Zeile):
  Start   -> {"ready": true, "device": "cuda", "model": "...", "load_s": 4.7}
  Anfrage <- {"wav": "<pfad>", "language": "de", "hotwords": "ChatGPT, Claude, ..."}
  Antwort -> {"ok": true, "text": "...", "audio_s": 91.1, "seconds": 3.2}
           | {"ok": false, "error": "..."}

Gemessen 13.10. auf der RTX 3070, 10 echte Diktate (9,9 min): large-v3-turbo
28x Echtzeit auf der GPU, 4,3x auf der CPU; 11,7 % Wortabweichung zum OpenAI-Text,
fast nur Schreibweise. Das deutsch nachtrainierte primeline-turbo liess ganze
Satzenden weg (34,6 %) und ist deshalb NICHT der Standard.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import site
import sys
import time
import wave

SAMPLE_RATE = 16000


def _cuda_dlls_sichtbar_machen() -> None:
    """cuBLAS aus dem nvidia-Wheel fuer ctranslate2 auffindbar machen (Windows)."""
    for sp in site.getsitepackages():
        for d in glob.glob(os.path.join(sp, "nvidia", "*", "bin")):
            os.add_dll_directory(d)
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


def _audio_laden(pfad: str):
    """16-kHz-Mono-PCM16 (so speichert Voice Flow) direkt lesen, sonst ueber PyAV."""
    import numpy as np

    with wave.open(pfad, "rb") as wf:
        passt = (wf.getframerate() == SAMPLE_RATE and wf.getnchannels() == 1
                 and wf.getsampwidth() == 2)
        if passt:
            roh = wf.readframes(wf.getnframes())
            return np.frombuffer(roh, dtype=np.int16).astype(np.float32) / 32768.0
    from faster_whisper.audio import decode_audio

    return decode_audio(pfad, sampling_rate=SAMPLE_RATE)


def _pyav_kompatibel_machen() -> None:
    """PyAV 19 kennt metadata_errors nicht mehr, faster-whisper 1.2.1 uebergibt es noch."""
    import av

    av_open = av.open
    av.open = lambda *a, **k: av_open(*a, **{x: y for x, y in k.items() if x != "metadata_errors"})


def _modell_laden(name: str):
    from faster_whisper import WhisperModel

    try:
        return WhisperModel(name, device="cuda", compute_type="float16"), "cuda"
    except Exception as ex:  # noqa: BLE001 - ohne GPU lieber langsam als gar nicht
        print(f"GPU nicht nutzbar ({ex}) - weiter auf der CPU", file=sys.stderr, flush=True)
        return WhisperModel(name, device="cpu", compute_type="int8"), "cpu"


def _segmente_verbinden(teile: list[str]) -> str:
    """Abschnitte zu Fliesstext verbinden.

    Ohne Vortext-Bindung (condition_on_previous_text=False) endet ein Abschnitt
    oft ohne Satzzeichen, der naechste beginnt gross: "...sehen scheisse aus Die
    ist geil" (gemessen 13.10.). Fehlt am Ende das Zeichen und beginnt der naechste
    Abschnitt gross, setzt das einen Punkt — Abschnittsgrenzen sind Sprechpausen.
    """
    text = ""
    for teil in (t.strip() for t in teile):
        if not teil:
            continue
        if text and text[-1] not in ".,;:!?…-" and teil[0].isupper():
            text += "."
        text = f"{text} {teil}" if text else teil
    return text


def _antworten(daten: dict) -> None:
    sys.stdout.write(json.dumps(daten, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="large-v3-turbo")
    args = parser.parse_args()

    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    _cuda_dlls_sichtbar_machen()
    _pyav_kompatibel_machen()
    t0 = time.time()
    modell, geraet = _modell_laden(args.model)
    _antworten({"ready": True, "device": geraet, "model": args.model,
                "load_s": round(time.time() - t0, 1)})

    for zeile in sys.stdin:
        if not zeile.strip():
            continue
        try:
            anfrage = json.loads(zeile)
            t = time.time()
            audio = _audio_laden(anfrage["wav"])
            segmente, info = modell.transcribe(
                audio,
                language=anfrage.get("language") or None,
                hotwords=anfrage.get("hotwords") or None,
                # Ohne Vortext-Bindung: mit ihr verstaerkte die Wortliste
                # Wiederholungsschleifen (gemessen 13.10., siehe local_transcription).
                condition_on_previous_text=False,
                beam_size=5,
                vad_filter=True,
            )
            text = _segmente_verbinden([s.text for s in segmente])
            _antworten({"ok": True, "text": text, "audio_s": round(info.duration, 1),
                        "seconds": round(time.time() - t, 1)})
        except Exception as ex:  # noqa: BLE001 - Fehler gehen als Antwort zurueck, Prozess lebt weiter
            _antworten({"ok": False, "error": f"{type(ex).__name__}: {ex}"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
