"""Screenshot-Marker proportional in ein Transkript einweben.

Reine Logik, keine I/O. Da die Transkription keine Wort-Zeitstempel liefert
(siehe transcription.py — gpt-4o-mini-transcribe gibt nur resp.text), platzieren
wir jeden Screenshot proportional: ein Shot bei Sekunde T einer D Sekunden langen
Aufnahme landet an der Textstelle bei ~ T/D, gesnappt auf eine Satzgrenze.
"""
from __future__ import annotations

import re

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def weave_screenshot_markers(
    text: str,
    captures: list[tuple[float, str]],
    duration: float,
) -> str:
    """Fuegt Screenshot-Marker proportional zur Aufnahmezeit in den Text ein.

    captures: Liste (offset_sekunden, marker_text), offset = Sekunden seit Aufnahme-Start.
    duration: Gesamtlaenge der Aufnahme in Sekunden.
    Platzierung: pro capture target = offset/duration -> Satz-Index, Marker NACH dem Satz.
    Robust: duration<=0 oder leerer Text -> Marker am Ende anhaengen (Reihenfolge erhalten).
    Mehrere captures: in Reihenfolge der offsets eingefuegt.
    """
    if not captures:
        return text

    ordered = sorted(captures, key=lambda c: c[0])

    # Leerer Text: nur die Marker, in offset-Reihenfolge.
    if not text.strip():
        return " ".join(marker for _, marker in ordered)

    sentences = _SENTENCE_SPLIT.split(text.strip())
    sentences = [s for s in sentences if s]
    if not sentences:
        sentences = [text.strip()]

    n = len(sentences)
    # Marker je Slot sammeln: slot in 0..n, Marker wird NACH sentence[slot-1] eingefuegt.
    by_slot: dict[int, list[str]] = {}
    for offset, marker in ordered:
        ratio = _clamp(offset / duration, 0.0, 1.0) if duration > 0 else 1.0
        idx = round(ratio * n)
        idx = max(0, min(n, idx))
        by_slot.setdefault(idx, []).append(marker)

    parts: list[str] = []
    for slot in range(n + 1):
        if slot > 0:
            parts.append(sentences[slot - 1])
        parts.extend(by_slot.get(slot, []))

    return " ".join(parts)
