from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

MAX_RETRIES = 1
RETRY_BACKOFF_SEC = 1.0

SYSTEM_PROMPT_TEMPLATE = """You are a text-cleanup tool for dictated text.

RULES:
1. Fix typos, grammar, and punctuation.
2. Correct proper nouns and domain-specific terms using the context below.
3. PRESERVE the user's direct tone. NO filler, NO politeness padding, NO embellishment.
4. NO interpretation, NO summarization, NO rewording beyond points 1-2.
5. Return ONLY the cleaned text. No comments, no markdown, no quotes.

CONTEXT (proper nouns, terms, projects):
{context}
"""


class Cleaner:
    """Anthropic Claude wrapper for text cleanup with custom vocabulary."""

    def __init__(
        self,
        api_key: str | None,
        model: str = "claude-haiku-4-5-20251001",
        context: str = "",
    ):
        self.model = model
        self.context = context
        self.client = None
        if api_key:
            try:
                from anthropic import Anthropic

                self.client = Anthropic(api_key=api_key)
            except ImportError:
                log.warning("anthropic package not installed; cleanup disabled.")

    @property
    def available(self) -> bool:
        return self.client is not None

    def cleanup(self, text: str) -> tuple[str, dict]:
        """Cleans text. Returns (cleaned_text, metadata)."""
        if not self.available or not text.strip():
            return text, {}

        system = SYSTEM_PROMPT_TEMPLATE.format(
            context=self.context or "(no context loaded)"
        )

        last_err: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = self.client.messages.create(  # type: ignore[union-attr]
                    model=self.model,
                    max_tokens=2000,
                    system=system,
                    messages=[{"role": "user", "content": text}],
                )
                # Bounds-check for content (e.g. stop_reason=content_filter returns empty).
                if not resp.content:
                    log.warning(
                        "Claude returned empty content (stop_reason=%s) — raw text returned.",
                        getattr(resp, "stop_reason", "?"),
                    )
                    return text, {"error": "empty_content"}
                cleaned = resp.content[0].text.strip()
                meta = {
                    "input_tokens": resp.usage.input_tokens,
                    "output_tokens": resp.usage.output_tokens,
                }
                return cleaned, meta
            except Exception as ex:
                last_err = ex
                if attempt < MAX_RETRIES:
                    sleep = RETRY_BACKOFF_SEC * (2**attempt)
                    log.warning(
                        "Claude cleanup failed (attempt %d/%d): %s — retry in %.1fs",
                        attempt + 1,
                        MAX_RETRIES + 1,
                        ex,
                        sleep,
                    )
                    time.sleep(sleep)

        # Fallback: return raw text instead of breaking the pipeline.
        log.error("Cleanup failed after retries, returning raw text: %s", last_err)
        return text, {"error": str(last_err)}
