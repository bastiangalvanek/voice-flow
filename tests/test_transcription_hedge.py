import threading
import time
import types

import pytest

from voice_flow import transcription as T
from voice_flow.transcription import Transcriber


class _Resp:
    def __init__(self, text):
        self.text = text


class _FakeCreate:
    """Simuliert audio.transcriptions.create mit pro-Call definiertem Verhalten.

    behaviors: Liste von (delay_sec, ergebnis_str | Exception). Call i nutzt
    behaviors[min(i, len-1)]. Thread-sicherer Zaehler.
    """

    def __init__(self, behaviors):
        self.behaviors = behaviors
        self.calls = 0
        self._lock = threading.Lock()

    def __call__(self, **kwargs):
        with self._lock:
            i = self.calls
            self.calls += 1
        delay, outcome = self.behaviors[min(i, len(self.behaviors) - 1)]
        time.sleep(delay)
        if isinstance(outcome, Exception):
            raise outcome
        return _Resp(outcome)


def _make(behaviors, monkeypatch, hedge_delay=0.15):
    monkeypatch.setattr(T, "HEDGE_DELAY_SEC", hedge_delay)
    tr = Transcriber.__new__(Transcriber)  # __init__ umgehen (kein echtes OpenAI)
    tr.model = "gpt-4o-mini-transcribe"
    fake = _FakeCreate(behaviors)
    tr.client = types.SimpleNamespace(
        audio=types.SimpleNamespace(
            transcriptions=types.SimpleNamespace(create=fake)
        )
    )
    return tr, fake


def test_fast_success_uses_single_call(monkeypatch):
    tr, fake = _make([(0.0, "hallo")], monkeypatch)
    resp = tr._create_with_hedge(b"x", "a.ogg", None, None)
    assert resp.text == "hallo"
    assert fake.calls == 1  # kein unnoetiger Hedge


def test_slow_first_call_gets_hedged_and_returns_fast(monkeypatch):
    # Call 0 haengt 1.0s (Spike), Call 1 (Hedge) sofort -> muss schnell zurueck.
    tr, fake = _make([(1.0, "slow"), (0.0, "fast")], monkeypatch, hedge_delay=0.15)
    t0 = time.monotonic()
    resp = tr._create_with_hedge(b"x", "a.ogg", None, None)
    dt = time.monotonic() - t0
    assert resp.text == "fast"
    assert dt < 0.6  # ~0.15s Hedge + sofort, NICHT 1.0s
    assert fake.calls == 2


def test_fast_error_raises_immediately_without_hedging(monkeypatch):
    # Schneller Fehler -> SOFORT hoch (kein paralleler Nachschuss = kein 429-
    # Hammering). Die aeussere Schleife klassifiziert/retryt. Nur 1 Call.
    tr, fake = _make([(0.0, RuntimeError("boom"))], monkeypatch)
    with pytest.raises(RuntimeError, match="boom"):
        tr._create_with_hedge(b"x", "a.ogg", None, None)
    assert fake.calls == 1  # NICHT gehedgt bei Fehler


def test_hedge_error_does_not_abandon_inflight_original(monkeypatch):
    # Original ist langsam (0.5s, dann Erfolg). Latenz-Hedge feuert nach 0.15s
    # und failt sofort. Der Fehler des Hedges darf das noch laufende Original
    # NICHT verwerfen -> Endergebnis = Original-Erfolg.
    tr, fake = _make(
        [(0.5, "original-ok"), (0.0, RuntimeError("hedge-failed"))],
        monkeypatch,
        hedge_delay=0.15,
    )
    resp = tr._create_with_hedge(b"x", "a.ogg", None, None)
    # Kern-Invariante: ein fehlschlagender Hedge verwirft das langsame Original
    # NICHT -> Endergebnis ist der Original-Erfolg. (Call-Count ist timing-
    # abhaengig: das langsame Original wird ggf. mehrfach gehedgt.)
    assert resp.text == "original-ok"
    assert fake.calls >= 2  # mindestens einmal gehedgt


def test_transcribe_integration_returns_stripped_text(monkeypatch):
    # to_opus stubben (kein echtes WAV noetig) -> Fallback-Upload, dann Hedge.
    monkeypatch.setattr(T, "to_opus", lambda b: None)
    tr, fake = _make([(0.0, "  text mit rand  ")], monkeypatch)
    out = tr.transcribe(b"RIFFfakewavdata", language="de")
    assert out == "text mit rand"
    assert fake.calls == 1
