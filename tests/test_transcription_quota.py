"""Leeres Guthaben kommt als 429 — darf aber nie als Frequenz-Limit gelten."""
from voice_flow.transcription import _ist_guthaben_leer


class FakeFehler:
    def __init__(self, code=None, typ=None, body=None):
        if code is not None:
            self.code = code
        if typ is not None:
            self.type = typ
        if body is not None:
            self.body = body


def test_code_credit_balance_exhausted():
    assert _ist_guthaben_leer(FakeFehler(code="credit_balance_exhausted")) is True


def test_typ_insufficient_quota():
    assert _ist_guthaben_leer(FakeFehler(typ="insufficient_quota")) is True


def test_koerper_wie_von_openai_geliefert():
    koerper = {"error": {"message": "You have no credits remaining.",
                         "type": "insufficient_quota",
                         "code": "credit_balance_exhausted"}}
    assert _ist_guthaben_leer(FakeFehler(body=koerper)) is True


def test_echtes_frequenz_limit_bleibt_retrybar():
    koerper = {"error": {"message": "Rate limit reached",
                         "type": "requests", "code": "rate_limit_exceeded"}}
    assert _ist_guthaben_leer(FakeFehler(code="rate_limit_exceeded", body=koerper)) is False


def test_leerer_fehler_ist_kein_guthaben_problem():
    assert _ist_guthaben_leer(FakeFehler()) is False


def test_transcribe_meldet_guthaben_sofort_und_wartet_nicht(monkeypatch):
    """Der echte Weg: transcribe() bekommt genau die 429 von OpenAI zurueck.

    Geprueft wird beides — die richtige Ausnahme UND dass keine 20 Sekunden
    verbraten werden. Der Fehlerkoerper ist woertlich der vom 20.08.2026.
    """
    import time

    import httpx
    from openai import RateLimitError

    from voice_flow import transcription as tr

    koerper = {"error": {"message": "You have no credits remaining.",
                         "type": "insufficient_quota", "param": None,
                         "code": "credit_balance_exhausted"}}
    antwort = httpx.Response(
        429, request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions"),
        json=koerper)

    t = tr.Transcriber(api_key="sk-test", model="whisper-1")

    def wirft(*_a, **_k):
        raise RateLimitError("429", response=antwort, body=koerper)

    monkeypatch.setattr(t, "_create_with_hedge", wirft)
    monkeypatch.setattr(tr, "to_opus", lambda _b: None)

    t0 = time.monotonic()
    try:
        t.transcribe(b"RIFF" + b"\x00" * 4000, language="de")
    except tr.TranscriberQuotaError as ex:
        assert "Guthaben" in str(ex)
    else:
        raise AssertionError("TranscriberQuotaError wurde nicht ausgeloest")
    assert time.monotonic() - t0 < 1.0, "es wurde trotzdem gewartet/wiederholt"
