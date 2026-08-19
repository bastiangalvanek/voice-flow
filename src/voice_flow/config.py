from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTEXT_FILE = PROJECT_ROOT / "galvanek_context.txt"
ENV_FILE = PROJECT_ROOT / ".env"
# 18.08: als gebuendelte App gibt es kein Repo-Verzeichnis mehr — dort liegt die
# .env im Benutzerordner. Reihenfolge: Repo zuerst (Entwicklung), dann Benutzer.
USER_ENV_FILE = Path.home() / ".voice-flow" / ".env"


@dataclass(frozen=True)
class Config:
    openai_api_key: str
    anthropic_api_key: str | None = None
    # 17.05 Bastian: zurueck auf F8 (Strg+Win ging nicht — Win-Taste wird vom
    # System abgefangen bevor keyboard-lib sie sieht, plus deutsche Tastatur
    # nennt Strg "strg" statt "ctrl"). F8 single-key ist robust + proven.
    # 13.08 Bastian (Mac): F8 ist auf dem MacBook die Play-Taste, F7 die
    # Zurueck-Taste — beide sollen der Musik gehoeren. Mac nimmt F5 (Aufnahme)
    # und F3 (Screenshot); Windows bleibt bei F8/F7.
    hotkey: str = "f5" if sys.platform == "darwin" else "f8"
    # 27.06 Bastian: F8 jetzt Toggle (1x = Start, nochmal = Stop). "hold" bleibt waehlbar.
    hotkey_mode: str = "toggle"  # "toggle" | "hold"
    # 27.06 Bastian: F7 = Screenshot des Monitors unter der Maus in den Session-Bucket.
    screenshot_hotkey: str = "f3" if sys.platform == "darwin" else "f7"
    # 27.06 Bastian: F6 = Loom-Zeichen-Overlay, dann Screenshot MIT Markierungen.
    annotate_hotkey: str = "f6"
    # 27.06 Bastian: Session-Buckets unter ~/voice-flow/sessions/<timestamp>/.
    sessions_dir: Path = field(default_factory=lambda: Path.home() / "voice-flow" / "sessions")
    quit_hotkey: str = "ctrl+shift+alt+q"
    # 19.08 Bastian: "wenn Bilder mal nicht mitgeliefert wurden oder man im
    # falschen Tab war — wieder Strg+V". Ein eigenes Kuerzel statt Strg+V selbst:
    # das normale Einfuegen darf systemweit nicht umgebogen werden.
    repaste_hotkey: str = "cmd+shift+v" if sys.platform == "darwin" else "ctrl+shift+v"
    # 07.07 Bastian "falsche Sprache, mega weird — auch bei ChatGPT im Web":
    # Grundursache ist das System-Mikro (Bluetooth-Headset im 8-kHz-Hands-Free-
    # Modus → matschiges Audio). Auf so verwaschenem Audio hat "auto" Whisper die
    # Sprache falsch raten lassen (Englisch/Spanisch-Halluzination). Default jetzt
    # "de" — eingestreute englische Woerter transkribiert Whisper trotzdem, aber
    # die Erkennung faellt nicht mehr auf eine Fremdsprache um.
    # Zurueck auf Auto-Detect: VOICE_FLOW_LANGUAGE=auto in .env.
    language: str = "de"
    # gpt-4o-mini-transcribe ist ~4x schneller als whisper-1 bei vergleichbarer
    # Qualitaet fuer Sprache. Default nach Bastians "schneller"-Wunsch (16.05).
    whisper_model: str = "gpt-4o-mini-transcribe"
    cleanup_model: str = "claude-haiku-4-5-20251001"
    sample_rate: int = 16000
    channels: int = 1
    audio_device: int | str | None = None
    min_recording_sec: float = 0.3
    enable_tray: bool = True
    enable_overlay: bool = True
    # 17.05 Bastian-Decision: NICHT always-visible (Wispr-Stil — Pille nur bei Action erscheinen).
    overlay_always_visible: bool = False
    enable_sound: bool = True
    # 17.05 Bastian-Decision: Cleanup default AUS (kein Anthropic-Key noetig).
    enable_cleanup: bool = False
    enable_audio_mute: bool = True
    # 17.05 v3 Bastian: nach F8-release den transkribierten Text in der Clipboard
    # belassen (False = NICHT restoren), damit er ihn ueberall mit Strg+V einfuegen
    # kann (auch wenn das Auto-Paste fehlschlug weil falsches Fenster aktiv war).
    enable_clipboard_restore: bool = False
    verbose: bool = False
    context: str = ""

    @property
    def cleanup_available(self) -> bool:
        return self.enable_cleanup and bool(self.anthropic_api_key)


def load_context() -> str:
    if not CONTEXT_FILE.exists():
        return ""
    return CONTEXT_FILE.read_text(encoding="utf-8").strip()


def load_config(overrides: dict | None = None) -> Config:
    for env_file in (ENV_FILE, USER_ENV_FILE):
        if env_file.exists():
            load_dotenv(env_file)

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise RuntimeError(
            "OPENAI_API_KEY fehlt. Lege .env aus .env.example an und trage deinen Key ein."
        )

    device_env = os.getenv("VOICE_FLOW_AUDIO_DEVICE")
    audio_device: int | str | None = None
    if device_env:
        # Zahl = fester Geraete-Index. Sonst = Name-Teil ("Poly") — robust gegen
        # wechselnde Indizes, matcht dein Mikro am Namen.
        try:
            audio_device = int(device_env)
        except ValueError:
            audio_device = device_env.strip()

    cfg = Config(
        openai_api_key=openai_key,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        hotkey=os.getenv("VOICE_FLOW_HOTKEY", "f5" if sys.platform == "darwin" else "f8"),
        hotkey_mode=os.getenv("VOICE_FLOW_HOTKEY_MODE", "toggle"),
        screenshot_hotkey=os.getenv("VOICE_FLOW_SCREENSHOT_HOTKEY", "f3" if sys.platform == "darwin" else "f7"),
        annotate_hotkey=os.getenv("VOICE_FLOW_ANNOTATE_HOTKEY", "f6"),
        repaste_hotkey=os.getenv(
            "VOICE_FLOW_REPASTE_HOTKEY",
            "cmd+shift+v" if sys.platform == "darwin" else "ctrl+shift+v"),
        language=os.getenv("VOICE_FLOW_LANGUAGE", "de"),
        whisper_model=os.getenv("VOICE_FLOW_WHISPER_MODEL", "gpt-4o-mini-transcribe"),
        cleanup_model=os.getenv(
            "VOICE_FLOW_CLEANUP_MODEL", "claude-haiku-4-5-20251001"
        ),
        audio_device=audio_device,
        context=load_context(),
    )

    if overrides:
        cfg = replace(cfg, **overrides)

    return cfg
