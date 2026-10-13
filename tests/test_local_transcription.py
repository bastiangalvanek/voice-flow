"""Ersatzweg OpenAI -> Grafikkarte (13.10.2026: Guthaben leer, zwei Diktate verloren)."""
from __future__ import annotations

from pathlib import Path

import pytest

from voice_flow.local_transcription import FallbackTranscriber, vocab_prompt
from voice_flow.transcription import TranscriberAuthError, TranscriberQuotaError

WAV = b"RIFF-test"


class FakeOpenAI:
    model = "gpt-4o-mini-transcribe"

    def __init__(self, fehler: Exception | None = None, text: str = "von OpenAI"):
        self.fehler, self.text, self.aufrufe = fehler, text, 0

    def transcribe(self, wav_bytes, language="auto", prompt=None):
        self.aufrufe += 1
        if self.fehler:
            raise self.fehler
        return self.text


class FakeLokal:
    model = "lokal:large-v3-turbo"

    def __init__(self, fehler: Exception | None = None, available: bool = True):
        self.fehler, self.available, self.aufrufe = fehler, available, 0

    def transcribe(self, wav_bytes, language="de", prompt=None):
        self.aufrufe += 1
        if self.fehler:
            raise self.fehler
        return "von der Grafikkarte"


def test_openai_klappt_lokal_bleibt_aus():
    lokal = FakeLokal()
    t = FallbackTranscriber(FakeOpenAI(), lokal)
    assert t.transcribe(WAV, language="de") == "von OpenAI"
    assert lokal.aufrufe == 0
    assert (t.last_engine, t.model, t.last_fallback_reason) == ("openai", "gpt-4o-mini-transcribe", None)


@pytest.mark.parametrize("fehler", [
    TranscriberQuotaError("Guthaben leer"),          # Vorfall 13.10.
    TranscriberAuthError("Key gesperrt"),            # Vorfall 12.10.
    RuntimeError("Whisper API failed after 3 attempts"),  # kein Netz / 5xx
])
def test_jeder_openai_ausfall_geht_auf_die_grafikkarte(fehler):
    t = FallbackTranscriber(FakeOpenAI(fehler), FakeLokal())
    assert t.transcribe(WAV, language="de") == "von der Grafikkarte"
    assert t.last_engine == "lokal"
    assert t.model == "lokal:large-v3-turbo"
    assert t.last_fallback_reason == type(fehler).__name__


def test_scheitert_auch_lokal_kommt_der_openai_fehler_hoch():
    """Die App zeigt dann wie bisher 'Guthaben aufgebraucht' und sichert die Aufnahme."""
    original = TranscriberQuotaError("Guthaben leer")
    t = FallbackTranscriber(FakeOpenAI(original), FakeLokal(RuntimeError("GPU weg")))
    with pytest.raises(TranscriberQuotaError) as info:
        t.transcribe(WAV)
    assert info.value is original


def test_ohne_installierte_lokale_erkennung_bleibt_alles_wie_bisher():
    lokal = FakeLokal(available=False)
    t = FallbackTranscriber(FakeOpenAI(TranscriberQuotaError("leer")), lokal)
    with pytest.raises(TranscriberQuotaError):
        t.transcribe(WAV)
    assert lokal.aufrufe == 0


def test_leeres_audio_wird_nicht_lokal_wiederholt():
    lokal = FakeLokal()
    t = FallbackTranscriber(FakeOpenAI(ValueError("Empty audio bytes")), lokal)
    with pytest.raises(ValueError):
        t.transcribe(WAV)
    assert lokal.aufrufe == 0


def test_modus_aus_fragt_nie_die_grafikkarte():
    lokal = FakeLokal()
    t = FallbackTranscriber(FakeOpenAI(TranscriberQuotaError("leer")), lokal, mode="aus")
    with pytest.raises(TranscriberQuotaError):
        t.transcribe(WAV)
    assert lokal.aufrufe == 0


def test_modus_lokal_fragt_openai_gar_nicht():
    openai = FakeOpenAI()
    t = FallbackTranscriber(openai, FakeLokal(), mode="lokal")
    assert t.transcribe(WAV) == "von der Grafikkarte"
    assert openai.aufrufe == 0
    assert t.last_fallback_reason is None  # kein Ausfall, sondern gewollt


def test_nach_einem_netzausfall_meldet_das_naechste_diktat_wieder_openai():
    openai = FakeOpenAI(RuntimeError("Whisper API failed after 3 attempts"))
    t = FallbackTranscriber(openai, FakeLokal())
    t.transcribe(WAV)
    openai.fehler = None
    assert t.transcribe(WAV) == "von OpenAI"
    assert (t.last_engine, t.last_fallback_reason) == ("openai", None)


def test_wortliste_kommt_aus_der_echten_kontextdatei():
    kontext = (Path(__file__).resolve().parents[1] / "galvanek_context.txt").read_text(encoding="utf-8")
    liste = vocab_prompt(kontext)
    assert liste.startswith("ChatGPT, ")
    # Kurz halten: die lange Liste erzeugte am 13.10. Halluzinationen.
    assert len(liste.split(",")) <= 20
    assert "Schreibweise" not in liste and "Wenn ich" not in liste


def test_ohne_wortliste_keine_vorgabe():
    assert vocab_prompt("Eigennamen: Bastian.\n\nSchreibweise:\n- Wenn ich X sage") is None
    assert vocab_prompt("") is None


def test_abschnitte_bekommen_an_der_sprechpause_einen_punkt():
    from voice_flow.local_stt_worker import _segmente_verbinden

    assert _segmente_verbinden([" die sehen scheisse aus", " Die ist geil, die Stange", " und weiter."]) == \
        "die sehen scheisse aus. Die ist geil, die Stange und weiter."
    assert _segmente_verbinden(["Schon fertig.", " Neuer Satz", "", " "]) == "Schon fertig. Neuer Satz"


def test_nach_leerem_guthaben_wird_openai_eine_weile_uebersprungen(monkeypatch):
    """Live 13.10. 22:07: 3,0 s von 8,4 s gingen nur fuers Abwarten der OpenAI-Absage drauf."""
    from voice_flow import local_transcription as lt

    jetzt = [1000.0]
    monkeypatch.setattr(lt.time, "monotonic", lambda: jetzt[0])
    openai, lokal = FakeOpenAI(TranscriberQuotaError("leer")), FakeLokal()
    t = FallbackTranscriber(openai, lokal)
    t.transcribe(WAV)
    assert openai.aufrufe == 1
    t.transcribe(WAV)  # innerhalb der Pause: OpenAI wird nicht gefragt
    assert (openai.aufrufe, lokal.aufrufe) == (1, 2)
    assert (t.last_engine, t.last_fallback_reason) == ("lokal", "TranscriberQuotaError")
    jetzt[0] += lt.OPENAI_PAUSE_SEC + 1
    openai.fehler = None
    assert t.transcribe(WAV) == "von OpenAI"  # nach der Pause wieder OpenAI zuerst


def test_netzfehler_pausiert_openai_nicht():
    openai = FakeOpenAI(RuntimeError("Whisper API failed after 3 attempts"))
    t = FallbackTranscriber(openai, FakeLokal())
    t.transcribe(WAV)
    t.transcribe(WAV)
    assert openai.aufrufe == 2


def test_scheitert_lokal_in_der_pause_wird_doch_openai_gefragt(monkeypatch):
    openai, lokal = FakeOpenAI(TranscriberAuthError("gesperrt")), FakeLokal()
    t = FallbackTranscriber(openai, lokal)
    t.transcribe(WAV)
    lokal.fehler, openai.fehler = RuntimeError("GPU weg"), None
    assert t.transcribe(WAV) == "von OpenAI"
    assert openai.aufrufe == 2
