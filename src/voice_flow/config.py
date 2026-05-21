from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTEXT_FILE = PROJECT_ROOT / "context.txt"
ENV_FILE = PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class Config:
    openai_api_key: str
    anthropic_api_key: str | None = None
    # F8 single-key is robust + universally available across keyboard layouts.
    hotkey: str = "f8"
    quit_hotkey: str = "ctrl+shift+alt+q"
    # "auto" → Whisper auto-detects language per recording.
    language: str = "auto"
    # gpt-4o-mini-transcribe is ~4x faster than whisper-1 with comparable quality.
    whisper_model: str = "gpt-4o-mini-transcribe"
    cleanup_model: str = "claude-haiku-4-5-20251001"
    sample_rate: int = 16000
    channels: int = 1
    audio_device: int | None = None
    min_recording_sec: float = 0.3
    enable_tray: bool = True
    enable_overlay: bool = True
    # Overlay pill only appears during action (not always-visible).
    overlay_always_visible: bool = False
    enable_sound: bool = True
    # Cleanup is opt-in: requires ANTHROPIC_API_KEY + explicit enable.
    enable_cleanup: bool = False
    enable_audio_mute: bool = True
    # After F8-release, leave transcribed text in clipboard so user can re-paste
    # manually with Ctrl+V if auto-paste landed in the wrong window.
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
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE)

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise RuntimeError(
            "OPENAI_API_KEY missing. Copy .env.example to .env and add your key."
        )

    device_env = os.getenv("VOICE_FLOW_AUDIO_DEVICE")
    audio_device: int | None = None
    if device_env:
        try:
            audio_device = int(device_env)
        except ValueError:
            # Loud-fail so the user notices their chosen device is being ignored.
            import logging
            logging.getLogger(__name__).warning(
                "VOICE_FLOW_AUDIO_DEVICE=%r is not a number — falling back to default mic.",
                device_env,
            )
            audio_device = None

    enable_cleanup_env = os.getenv("VOICE_FLOW_ENABLE_CLEANUP")
    enable_cleanup = bool(enable_cleanup_env and enable_cleanup_env not in ("0", "false", "False", ""))

    cfg = Config(
        openai_api_key=openai_key,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        hotkey=os.getenv("VOICE_FLOW_HOTKEY", "f8"),
        language=os.getenv("VOICE_FLOW_LANGUAGE", "auto"),
        whisper_model=os.getenv("VOICE_FLOW_WHISPER_MODEL", "gpt-4o-mini-transcribe"),
        cleanup_model=os.getenv(
            "VOICE_FLOW_CLEANUP_MODEL", "claude-haiku-4-5-20251001"
        ),
        audio_device=audio_device,
        enable_cleanup=enable_cleanup,
        context=load_context(),
    )

    if overrides:
        cfg = replace(cfg, **overrides)

    return cfg
