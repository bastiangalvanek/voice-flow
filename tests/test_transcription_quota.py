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
