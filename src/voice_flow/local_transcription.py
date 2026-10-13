"""Lokaler Ersatzweg: scheitert OpenAI, verschriftet die Grafikkarte.

13.10.2026: OpenAI meldete "credit_balance_exhausted", zwei Diktate (91 s, 177 s)
landeten als _failed im Ordner, am 12.10. dasselbe mit dem gesperrten Schluessel.
Bastian: "bau ein, mit Wortliste und Grafikkarte". Ergebnis: Voice Flow fragt
weiter zuerst OpenAI (beste Namen-Erkennung); kommt dort nichts zurueck — Guthaben
leer, Schluessel abgelehnt, kein Netz —, laeuft dasselbe Audio durch
large-v3-turbo auf der eigenen Grafikkarte. Ein Diktat geht nicht mehr verloren.

Die Erkennung selbst laeuft in einem eigenen Prozess mit eigener venv
(.venv-lokal, siehe local_stt_worker.py), damit die taegliche Diktier-venv keine
CUDA-Pakete bekommt (pip-Unfall 29.09.: ein Paket-Update hat dort die App zerlegt).
"""
from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from voice_flow.audio_chunks import wav_duration_seconds
from voice_flow.config import PROJECT_ROOT, Config
from voice_flow.transcription import Transcriber

log = logging.getLogger(__name__)

LOCAL_VENV = PROJECT_ROOT / ".venv-lokal"
WORKER_SCRIPT = Path(__file__).with_name("local_stt_worker.py")
WORKER_LOG = Path.home() / ".voice-flow" / "logs" / "lokal-stt.log"
TEMP_DIR = Path.home() / ".voice-flow" / "tmp"

# Modell laden: gemessen 4,7 s (GPU, aus dem Cache). Erster Download waere ~1,6 GB.
START_TIMEOUT_SEC = 180
# Gemessen GPU 28x, CPU 4,3x Echtzeit. Grosszuegig, damit auch der CPU-Notweg
# ein langes Diktat schafft: Grundzeit plus halbe Audiodauer.
BASE_TIMEOUT_SEC = 60
TIMEOUT_PER_AUDIO_SEC = 0.5

# Wortliste: eine eigene Zeile in galvanek_context.txt. Gemessen 13.10. auf 10 echten
# Diktaten: die volle 700-Zeichen-Begriffsliste als initial_prompt verschlechterte
# die Abweichung von 11,7 % auf 20,3 % (Wiederholungsschleifen, fremde Schrift);
# 15 Begriffe als hotwords ohne Vortext-Bindung: 11,2 %, ChatGPT/CleverPV richtig.
VOCAB_HEADER = "Lokale Wortliste"


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def vocab_prompt(context: str) -> str | None:
    """Begriffe der Zeile 'Lokale Wortliste ...: A, B, C' aus galvanek_context.txt."""
    for zeile in (context or "").splitlines():
        if zeile.startswith(VOCAB_HEADER) and ":" in zeile:
            return zeile.split(":", 1)[1].strip().rstrip(".") or None
    return None


class LocalTranscriber:
    """Spricht mit dem Worker-Prozess. Startet ihn beim ersten Bedarf, haelt ihn warm."""

    def __init__(self, model: str = "large-v3-turbo", venv: Path = LOCAL_VENV,
                 vocab: str | None = None):
        self.model_name = model
        self.model = f"lokal:{model}"
        self.python = _venv_python(venv)
        self.vocab = vocab
        self._proc: subprocess.Popen | None = None
        self._stderr = None
        self._antworten: queue.Queue = queue.Queue()
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self.python.exists() and WORKER_SCRIPT.exists()

    def _starten(self) -> None:
        WORKER_LOG.parent.mkdir(parents=True, exist_ok=True)
        self._stderr = open(WORKER_LOG, "a", encoding="utf-8")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # pythonw-App: kein Konsolenfenster
        self._proc = subprocess.Popen(
            [str(self.python), str(WORKER_SCRIPT), "--model", self.model_name],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._stderr,
            text=True, encoding="utf-8", bufsize=1, creationflags=flags,
            env={**os.environ, "HF_HUB_DISABLE_SYMLINKS_WARNING": "1"},
        )
        self._antworten = queue.Queue()
        proc = self._proc

        def lesen() -> None:
            for zeile in proc.stdout:
                self._antworten.put(zeile)
            self._antworten.put(None)  # Prozess beendet

        threading.Thread(target=lesen, daemon=True, name="lokal-stt-leser").start()
        bereit = self._warten(START_TIMEOUT_SEC)
        log.info("LOKAL  Modell %s bereit auf %s (%.1fs geladen)",
                 bereit.get("model"), bereit.get("device"), bereit.get("load_s", 0))

    def _warten(self, timeout: float) -> dict:
        try:
            zeile = self._antworten.get(timeout=timeout)
        except queue.Empty:
            self.stop()
            raise RuntimeError(f"Lokale Erkennung antwortet nicht binnen {timeout:.0f}s")
        if zeile is None:
            self.stop()
            raise RuntimeError(f"Lokale Erkennung beendet — Details in {WORKER_LOG}")
        return json.loads(zeile)

    def transcribe(self, wav_bytes: bytes, language: str = "de",
                   prompt: str | None = None) -> str:
        """Gleiche Signatur wie Transcriber. prompt (OpenAI-Kontext) wird durch
        die eigene Wortliste ersetzt — die ist fuer Whisper gebaut."""
        if not wav_bytes:
            raise ValueError("Empty audio bytes — kann nichts transkribieren.")
        if not self.available:
            raise RuntimeError(f"Lokale Erkennung nicht installiert ({self.python} fehlt)")
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._starten()
            fd, pfad = tempfile.mkstemp(suffix=".wav", dir=TEMP_DIR)
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(wav_bytes)
                anfrage = {"wav": pfad,
                           "language": None if language in ("auto", "", None) else language,
                           "hotwords": self.vocab}
                self._proc.stdin.write(json.dumps(anfrage, ensure_ascii=False) + "\n")
                self._proc.stdin.flush()
                timeout = BASE_TIMEOUT_SEC + TIMEOUT_PER_AUDIO_SEC * wav_duration_seconds(wav_bytes)
                antwort = self._warten(timeout)
            finally:
                Path(pfad).unlink(missing_ok=True)
        if not antwort.get("ok"):
            raise RuntimeError(f"Lokale Erkennung fehlgeschlagen: {antwort.get('error')}")
        log.info("LOKAL  %.1fs Audio in %.1fs", antwort.get("audio_s", 0), antwort.get("seconds", 0))
        return antwort.get("text", "")

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            proc.kill()
        stderr, self._stderr = self._stderr, None
        if stderr is not None:
            stderr.close()


class FallbackTranscriber:
    """Erst OpenAI, bei jedem Fehlschlag dort die lokale Erkennung.

    mode: "fallback" (Standard) · "lokal" (nur Grafikkarte) · "aus" (nur OpenAI).
    Scheitert auch der lokale Weg, geht der ORIGINALE OpenAI-Fehler hoch — die
    App zeigt dann wie bisher "Guthaben leer" / "Key ungueltig" und sichert die
    Aufnahme als _failed.
    """

    def __init__(self, primary: Transcriber, local: LocalTranscriber | None, mode: str = "fallback"):
        self.primary = primary
        self.local = local
        self.mode = mode
        self.last_engine = "openai"
        self.last_fallback_reason: str | None = None

    @property
    def model(self) -> str:
        return self.local.model if self.last_engine == "lokal" and self.local else self.primary.model

    def _lokal(self, wav_bytes: bytes, language: str) -> str:
        text = self.local.transcribe(wav_bytes, language=language)
        self.last_engine = "lokal"
        return text

    def transcribe(self, wav_bytes: bytes, language: str = "auto", prompt: str | None = None) -> str:
        self.last_engine, self.last_fallback_reason = "openai", None
        if self.mode == "lokal" and self.local is not None:
            return self._lokal(wav_bytes, language)
        try:
            return self.primary.transcribe(wav_bytes, language=language, prompt=prompt)
        except ValueError:
            raise  # leeres Audio — lokal kaeme dasselbe heraus
        except Exception as ex:  # noqa: BLE001 - jeder OpenAI-Ausfall soll lokal aufgefangen werden
            if self.mode != "fallback" or self.local is None or not self.local.available:
                raise
            self.last_fallback_reason = type(ex).__name__
            log.warning("LOKAL  OpenAI fehlgeschlagen (%s) — verschrifte auf der Grafikkarte.",
                        self.last_fallback_reason)
            try:
                return self._lokal(wav_bytes, language)
            except Exception as lokal_ex:  # noqa: BLE001 - Original-Fehler ist der aussagekraeftigere
                log.error("LOKAL  ebenfalls fehlgeschlagen: %s", lokal_ex)
                raise ex from lokal_ex


def build_transcriber(config: Config) -> FallbackTranscriber:
    primary = Transcriber(api_key=config.openai_api_key, model=config.whisper_model)
    local = None
    if config.local_stt != "aus":
        local = LocalTranscriber(model=config.local_stt_model, vocab=vocab_prompt(config.context))
        if not local.available:
            log.warning("LOKAL  nicht installiert (%s fehlt) — nur OpenAI.", local.python)
    return FallbackTranscriber(primary, local, mode=config.local_stt)
