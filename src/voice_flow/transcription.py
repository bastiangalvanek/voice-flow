from __future__ import annotations

import io
import logging
import queue
import threading
import time

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

from voice_flow.audio_encode import to_opus
from voice_flow.config import ENV_FILE

log = logging.getLogger(__name__)


MAX_RETRIES = 2
RETRY_BACKOFF_SEC = 1.0
DEFAULT_RATE_LIMIT_WAIT_SEC = 20  # OpenAI typischerweise

# 28.06 Bastian "schneller, zu lang": Die OpenAI-Transcription-Latenz ist nach der
# Opus-Kompression nicht mehr upload-bound, sondern hat eine schwere SCHWANZ-
# Verteilung: gemessen Median ~0.7s, aber ~15% der Requests spiken auf 3-10s
# (rein server-seitig, zufaellig, nicht reproduzierbar). Gegenmittel: Request-
# Hedging (Dean/Barroso "Tail at Scale"). Kommt der erste Call nicht binnen
# HEDGE_DELAY_SEC zurueck, feuert ein PARALLELER Backup; der erste Erfolg gewinnt.
# Kein Cancel -> ein legitim langsamer (langer) Call wird nie abgewuergt, nur
# ueberholt. Kappt den Spike (9.8s -> ~3s) zum Preis seltener Doppel-Calls.
HEDGE_DELAY_SEC = 2.0
HEDGE_MAX_INFLIGHT = 3  # Original + bis zu 2 Backups (deckt ~99,7% der Spikes)


class TranscriberAuthError(RuntimeError):
    """Raised when OpenAI rejects the API key (401). Not retryable."""


class Transcriber:
    """OpenAI Audio Transcription API Wrapper mit selektivem Retry.

    Retryable: APIConnectionError, APITimeoutError, RateLimitError, 5xx APIError.
    Nicht retryable (Critic P1-10): AuthenticationError (401), ValueError, andere.

    Modell-spezifisches Verhalten (Critic P1-11):
    - whisper-1: prompt= ist Audio-Continuation-Hint (gut fuer Eigennamen).
    - gpt-4o-(mini-)transcribe: prompt= wird als Chat-Instruction interpretiert
      und kann das Modell verwirren → wir senden bei diesen Modellen KEINEN prompt.
    """

    def __init__(self, api_key: str, model: str = "whisper-1"):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def _supports_prompt_as_vocab_hint(self) -> bool:
        """True nur fuer whisper-1; gpt-4o-Modelle behandeln prompt anders."""
        m = self.model.lower()
        return m == "whisper-1" or m.startswith("whisper-")

    def transcribe(
        self,
        wav_bytes: bytes,
        language: str = "auto",
        prompt: str | None = None,
    ) -> str:
        if not wav_bytes:
            raise ValueError("Empty audio bytes — kann nichts transkribieren.")

        # Bei gpt-4o-Modellen: prompt nicht senden (siehe Critic P1-11)
        effective_prompt = prompt if self._supports_prompt_as_vocab_hint() else None
        # 17.05 v2: "auto" → None (Whisper auto-detect, multilingual). Sonst ISO-Code.
        effective_language = None if language in ("auto", "", None) else language

        # 28.06 Bastian "schneller": Audio EINMAL als Opus komprimieren (gemessen
        # 2.3x schneller, ~10x kleinerer Upload, gleiche Transkription). Bei
        # Fehler Fallback auf WAV. Vor der Retry-Schleife -> nicht pro Versuch neu.
        opus_bytes = to_opus(wav_bytes)
        if opus_bytes is not None:
            upload_bytes, upload_name = opus_bytes, "audio.ogg"
            log.debug(
                "Upload Opus %d KB (statt WAV %d KB).",
                len(opus_bytes) // 1024,
                len(wav_bytes) // 1024,
            )
        else:
            upload_bytes, upload_name = wav_bytes, "audio.wav"

        last_err: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                # Latenz-Hedging kapselt den eigentlichen API-Call; Fehler werden
                # unveraendert hochgereicht und unten klassifiziert/retryt.
                resp = self._create_with_hedge(
                    upload_bytes, upload_name, effective_language, effective_prompt
                )
                return (resp.text or "").strip()

            except AuthenticationError as ex:
                # 401 — Key falsch/fehlt. Retry sinnlos. (Critic P2-18: ENV_FILE benutzen)
                log.error("OpenAI lehnt API-Key ab (401). Kein Retry. %s", ex)
                raise TranscriberAuthError(
                    "OpenAI lehnt deinen API-Key ab.\n\n"
                    f"Pruefe .env:\n{ENV_FILE}\n\n"
                    "OPENAI_API_KEY=sk-... durch deinen echten Key ersetzen,\n"
                    "dann Voice Flow neu starten."
                ) from ex

            except RateLimitError as ex:
                # Critic P1-11: Retry-After-Header honorieren wenn OpenAI ihn sendet
                last_err = ex
                wait = DEFAULT_RATE_LIMIT_WAIT_SEC
                try:
                    if hasattr(ex, "response") and ex.response is not None:
                        retry_after = ex.response.headers.get("retry-after")
                        if retry_after:
                            wait = int(float(retry_after))
                except Exception:
                    pass
                if attempt < MAX_RETRIES:
                    log.warning(
                        "OpenAI rate-limited (attempt %d/%d) — wait %ds",
                        attempt + 1,
                        MAX_RETRIES + 1,
                        wait,
                    )
                    time.sleep(wait)
                continue

            except (APIConnectionError, APITimeoutError) as ex:
                # Netzwerk/Timeout — retryable
                last_err = ex
                if attempt < MAX_RETRIES:
                    sleep = RETRY_BACKOFF_SEC * (2**attempt)
                    log.warning(
                        "Whisper Netzwerk-Fehler (attempt %d/%d): %s — retry in %.1fs",
                        attempt + 1,
                        MAX_RETRIES + 1,
                        ex,
                        sleep,
                    )
                    time.sleep(sleep)
                continue

            except APIError as ex:
                # Restliche API-Errors: 5xx ist retryable, 4xx nicht
                status = getattr(ex, "status_code", None)
                is_retryable = status is None or status >= 500
                last_err = ex
                if is_retryable and attempt < MAX_RETRIES:
                    sleep = RETRY_BACKOFF_SEC * (2**attempt)
                    log.warning(
                        "Whisper API %s (attempt %d/%d) — retry in %.1fs",
                        status,
                        attempt + 1,
                        MAX_RETRIES + 1,
                        sleep,
                    )
                    time.sleep(sleep)
                    continue
                # Nicht retryable 4xx — sofort raisen, kein Time-Waste
                log.error("Whisper API %s — kein Retry: %s", status, ex)
                raise

        raise RuntimeError(
            f"Whisper API failed after {MAX_RETRIES + 1} attempts"
        ) from last_err

    def _create_with_hedge(
        self,
        upload_bytes: bytes,
        upload_name: str,
        language: str | None,
        prompt: str | None,
    ):
        """Ein Transcription-Call mit Latenz-Hedging (siehe HEDGE_DELAY_SEC).

        Feuert den Call; kommt binnen HEDGE_DELAY_SEC kein Ergebnis, startet ein
        PARALLELER Backup (bis HEDGE_MAX_INFLIGHT). Der erste Erfolg gewinnt und
        wird zurueckgegeben; verlierende Calls laufen als Daemon-Threads aus und
        werden ignoriert (kein Cancel — ein langer, legitimer Call wird nie
        abgewuergt). Schlagen ALLE gestarteten Versuche fehl, wird der erste
        Fehler hochgereicht -> die aeussere Schleife klassifiziert/retryt ihn.
        """
        results: queue.Queue = queue.Queue()

        def attempt() -> None:
            # Jeder Versuch braucht einen FRISCHEN BytesIO (Cursor/Verbrauch).
            buf = io.BytesIO(upload_bytes)
            buf.name = upload_name
            kwargs = {"model": self.model, "file": buf}
            if language is not None:
                kwargs["language"] = language
            if prompt is not None:
                kwargs["prompt"] = prompt
            try:
                results.put((True, self.client.audio.transcriptions.create(**kwargs)))
            except Exception as ex:  # noqa: BLE001 - klassifiziert die aeussere Schleife
                results.put((False, ex))

        def launch() -> None:
            threading.Thread(target=attempt, daemon=True, name="whisper-hedge").start()

        launch()
        started = 1
        errored = 0
        first_error: Exception | None = None
        deadline = time.monotonic() + HEDGE_DELAY_SEC

        while True:
            can_hedge = started < HEDGE_MAX_INFLIGHT
            wait = max(0.0, deadline - time.monotonic()) if can_hedge else None
            try:
                ok, payload = results.get(timeout=wait)
            except queue.Empty:
                # Erster Call zu langsam -> parallelen Backup feuern (kein Cancel).
                launch()
                started += 1
                deadline = time.monotonic() + HEDGE_DELAY_SEC
                continue

            if ok:
                return payload  # schnellster Erfolg gewinnt

            # Ein Versuch ist fehlgeschlagen. KEIN paralleler Nachschuss bei
            # Fehler — das wuerde bei 429/5xx den Server HAMMERN statt zu
            # backoffen (Critic P1-3). Gehedgt wird AUSSCHLIESSLICH auf Latenz
            # (Empty-Timeout oben). Sobald kein Versuch mehr laeuft, geht der
            # erste Fehler hoch; die aeussere Schleife klassifiziert/retryt ihn
            # mit korrektem Backoff/retry-after (auth=fatal, 429=warten).
            errored += 1
            first_error = first_error or payload
            if errored >= started:
                raise first_error
            # Sonst: noch ein (Latenz-)Hedge in-flight -> auf ihn warten, er kann
            # noch erfolgreich sein (Fehler eines Hedges verwirft das Original nicht).
