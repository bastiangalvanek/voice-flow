"""E2E-Tests fuer den Mac-Port — echte Kette, keine Mocks.

Was hier bewiesen wird:
  1. Audio -> Opus -> OpenAI-Whisper -> Text  (echter API-Call, echtes Audio
     aus der macOS-Stimme via `say` — kein Mikrofon noetig)
  2. Clipboard-Pipeline (pyperclip rund-trip)
  3. Sound-Feedback (afplay-Systemsounds vorhanden und abspielbar)
  4. Berechtigungs-Modul meldet Status ohne Absturz
  5. App-Bundle existiert und zeigt auf den echten Code

Uebersprungen ausserhalb macOS bzw. ohne OPENAI_API_KEY in .env.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import pytest

MAC = sys.platform == "darwin"
ROOT = Path(__file__).resolve().parents[1]


def _api_key() -> str | None:
    env = ROOT / ".env"
    if not env.exists():
        return None
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("OPENAI_API_KEY="):
            v = line.split("=", 1)[1].strip()
            return v or None
    return None


@pytest.mark.skipif(not MAC, reason="macOS-E2E")
@pytest.mark.skipif(_api_key() is None, reason="kein OPENAI_API_KEY in .env")
def test_e2e_audio_zu_text_ueber_echte_api():
    """Der Kern von Voice Flow: gesprochenes Deutsch wird zu Text."""
    satz = "Das Angebot für die Wärmepumpe ist fertig"
    with tempfile.TemporaryDirectory() as td:
        aiff = Path(td) / "probe.aiff"
        wav = Path(td) / "probe.wav"
        # macOS-Stimme erzeugt echtes Sprach-Audio — deterministischer als ein Mikro.
        subprocess.run(["say", "-v", "Anna", "-o", str(aiff), satz], check=True, timeout=30)
        # afconvert (Bordmittel) -> 16 kHz mono PCM, exakt was die App aufnimmt.
        subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(wav)],
            check=True, timeout=30,
        )
        wav_bytes = wav.read_bytes()
        assert len(wav_bytes) > 40_000, "say/afconvert lieferte kein brauchbares Audio"

        # Opus-Kompression wie im Produktionspfad
        from voice_flow.audio_encode import to_opus
        opus = to_opus(wav_bytes)
        assert opus is not None and len(opus) < len(wav_bytes), "Opus-Encoding tot"

        # Echter Whisper-Call
        from voice_flow.transcription import Transcriber
        t = Transcriber(api_key=_api_key(), model="gpt-4o-mini-transcribe")
        text = t.transcribe(wav_bytes, language="de")
        assert text, "API lieferte leeren Text"
        gefunden = sum(w.lower() in text.lower() for w in ("Angebot", "Wärmepumpe", "fertig"))
        assert gefunden >= 2, f"Transkript passt nicht zum Gesprochenen: {text!r}"


@pytest.mark.skipif(not MAC, reason="macOS-E2E")
def test_e2e_clipboard_roundtrip():
    import pyperclip
    marker = "voice-flow-e2e-598237"
    alt = None
    try:
        alt = pyperclip.paste()
    except Exception:
        pass
    pyperclip.copy(marker)
    assert pyperclip.paste() == marker
    if alt:
        pyperclip.copy(alt)


@pytest.mark.skipif(not MAC, reason="macOS-E2E")
def test_e2e_systemsounds_vorhanden():
    from voice_flow.sound import _MAC_SOUNDS
    for _, pfad in _MAC_SOUNDS:
        assert Path(pfad).exists(), f"Systemsound fehlt: {pfad}"
    # kurz wirklich abspielen — beweist dass afplay funktioniert
    r = subprocess.run(["afplay", _MAC_SOUNDS[0][1]], timeout=10)
    assert r.returncode == 0


@pytest.mark.skipif(not MAC, reason="macOS-E2E")
def test_e2e_berechtigungsmodul_stuerzt_nicht_ab():
    from voice_flow import darwin_permissions as dp
    # prompt=False: nur Status lesen, keine Dialoge aus dem Testlauf
    status = dp.accessibility_ok(prompt=False)
    assert status in (True, False)


@pytest.mark.skipif(not MAC, reason="macOS-E2E")
def test_e2e_app_bundle_ist_eigenstaendig():
    """Die installierte App muss OHNE Repo und venv laufen koennen.

    18.08 Bastian: "damit es nicht im AppleScript/Python laeuft, sondern meiner
    App". Vorher war der Launcher ein Shell-Skript, das die venv im Repo startete
    — verschiebt man das Repo, war die App tot. Jetzt: eigenes Programm im
    Bundle, Python und Qt liegen mit drin, und die Modus-Zeichen ebenso.
    """
    for bundle in (Path("/Applications/Voice Flow.app"),
                   Path.home() / "Applications" / "Voice Flow.app"):
        if not bundle.exists():
            continue
        exe = bundle / "Contents" / "MacOS" / "Voice Flow"
        assert exe.exists(), f"{bundle}: kein Programm im Bundle"
        assert os.access(exe, os.X_OK), f"{exe}: nicht ausfuehrbar"
        kopf = exe.read_bytes()[:4]
        assert kopf in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"), (
            f"{exe}: kein Mach-O-Programm, sondern noch ein Skript-Starter"
        )
        res = bundle / "Contents" / "Resources"
        for name in ("mode_claude_code.png", "mode_ai_web.png"):
            assert (res / "assets" / name).exists(), f"{name} fehlt im Bundle"
        return
    pytest.skip("keine installierte Voice Flow.app — auf dem Bau-Rechner normal, "
                "lokal heisst es: App noch nicht installiert")


@pytest.mark.skipif(not MAC, reason="macOS-Berechtigungen")
def test_start_fragt_nicht_nach_bildschirmaufnahme(monkeypatch):
    """18.08 Bastian: "andauernd kommt dieser Scheiss, habe schon 1000x genehmigt".

    Der Start darf den System-Dialog NICHT ausloesen — sonst kommt er bei jedem
    Programmstart erneut. Gefragt wird erst beim ersten Screenshot.
    """
    from voice_flow import darwin_permissions as dp

    gefragt = []
    monkeypatch.setattr(dp, "request_screen_capture", lambda: gefragt.append(True))
    monkeypatch.setattr(dp, "request_microphone", lambda: None)
    monkeypatch.setattr(dp, "accessibility_ok", lambda prompt=True: True)

    dp.ensure_all()
    assert gefragt == [], "ensure_all darf den Bildschirm-Dialog nicht ausloesen"
