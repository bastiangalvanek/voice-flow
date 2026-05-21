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
DEFAULT_RATE_LIMIT_WAIT_SEC = 20  # typical OpenAI rate-limit window


class TranscriberAuthError(RuntimeError):
    """Raised when OpenAI rejects the API key (401). Not retryable."""


class Transcriber:
    """OpenAI Audio Transcription API wrapper with selective retry.

    Retryable: APIConnectionError, APITimeoutError, RateLimitError, 5xx APIError.
    Not retryable: AuthenticationError (401), ValueError, others.

    Model-specific behavior:
    - whisper-1: prompt= is an audio-continuation hint (good for proper nouns).
    - gpt-4o-(mini-)transcribe: prompt= is interpreted as a chat instruction and
      can confuse the model → we send NO prompt for those models.
    """

    def __init__(self, api_key: str, model: str = "whisper-1"):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def _supports_prompt_as_vocab_hint(self) -> bool:
        """True only for whisper-1; gpt-4o models treat prompt differently."""
        m = self.model.lower()
        return m == "whisper-1" or m.startswith("whisper-")

    def transcribe(
        self,
        wav_bytes: bytes,
        language: str = "auto",
        prompt: str | None = None,
    ) -> str:
        if not wav_bytes:
            raise ValueError("Empty audio bytes — nothing to transcribe.")

        effective_prompt = prompt if self._supports_prompt_as_vocab_hint() else None
        effective_language = None if language in ("auto", "", None) else language

        last_err: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                buf = io.BytesIO(wav_bytes)
                buf.name = "audio.wav"
                kwargs = {"model": self.model, "file": buf}
                if effective_language is not None:
                    kwargs["language"] = effective_language
                if effective_prompt is not None:
                    kwargs["prompt"] = effective_prompt
                resp = self.client.audio.transcriptions.create(**kwargs)
                return (resp.text or "").strip()

            except AuthenticationError as ex:
                log.error("OpenAI rejected the API key (401). No retry. %s", ex)
                raise TranscriberAuthError(
                    "OpenAI rejected your API key.\n\n"
                    f"Check .env:\n{ENV_FILE}\n\n"
                    "Replace OPENAI_API_KEY=sk-... with your real key,\n"
                    "then restart Voice Flow."
                ) from ex

            except RateLimitError as ex:
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
                last_err = ex
                if attempt < MAX_RETRIES:
                    sleep = RETRY_BACKOFF_SEC * (2**attempt)
                    log.warning(
                        "Whisper network error (attempt %d/%d): %s — retry in %.1fs",
                        attempt + 1,
                        MAX_RETRIES + 1,
                        ex,
                        sleep,
                    )
                    time.sleep(sleep)
                continue

            except APIError as ex:
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
                log.error("Whisper API %s — no retry: %s", status, ex)
                raise

        raise RuntimeError(
            f"Whisper API failed after {MAX_RETRIES + 1} attempts"
        ) from last_err
