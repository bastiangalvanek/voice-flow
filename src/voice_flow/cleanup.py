from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

MAX_RETRIES = 1
RETRY_BACKOFF_SEC = 1.0

SYSTEM_PROMPT_TEMPLATE = """Du bist ein Text-Cleanup-Tool fuer diktierten Text von Bastian Galvanek.

REGELN:
1. Korrigiere Tippfehler, Grammatik, Satzzeichen.
2. Korrigiere Eigennamen und Fachbegriffe nach dem Kontext unten.
3. BEHALTE Bastians direkten Stil. KEINE Floskeln, KEIN Hoeflichkeits-Bla, KEINE Verschoenerung.
4. KEINE Interpretation, KEINE Zusammenfassung, KEINE Umformulierung ueber Punkte 1-2 hinaus.
5. Gib NUR den bereinigten Text zurueck. Kein Kommentar, kein Markdown, keine Anfuehrungszeichen.

KONTEXT (Eigennamen, Fachbegriffe, Projekte):
{context}
"""


class Cleaner:
    """Anthropic Claude Wrapper fuer Text-Cleanup mit Custom-Vokabular."""

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
        """Bereinigt Text. Returns (cleaned_text, metadata)."""
        if not self.available or not text.strip():
            return text, {}

        system = SYSTEM_PROMPT_TEMPLATE.format(
            context=self.context or "(kein Kontext geladen)"
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
                # Critic P2-19: Bounds-Check fuer content (z.B. bei content_filter stop_reason)
                if not resp.content:
                    log.warning("Claude returned empty content (stop_reason=%s) — Rohtext.", getattr(resp, "stop_reason", "?"))
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

        # Fallback: gib raw text zurueck statt Pipeline zu sprengen
        log.error("Cleanup failed after retries, returning raw text: %s", last_err)
        return text, {"error": str(last_err)}
