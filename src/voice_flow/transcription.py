from __future__ import annotations

import io
import logging
import time

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

from voice_flow.config import ENV_FILE

log = logging.getLogger(__name__)


MAX_RETRIES = 2
RETRY_BACKOFF_SEC = 1.0
DEFAULT_RATE_LIMIT_WAIT_SEC = 20  # OpenAI typischerweise


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

        last_err: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                buf = io.BytesIO(wav_bytes)
                buf.name = "audio.wav"
                # API akzeptiert None nicht direkt fuer language → omit key
                kwargs = {"model": self.model, "file": buf}
                if effective_language is not None:
                    kwargs["language"] = effective_language
                if effective_prompt is not None:
                    kwargs["prompt"] = effective_prompt
                resp = self.client.audio.transcriptions.create(**kwargs)
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
