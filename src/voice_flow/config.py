from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv

log = logging.getLogger(__name__)


def _is_frozen() -> bool:
    """True when running inside a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def _project_root() -> Path:
    """Folder that holds the running app.

    - PyInstaller bundle: the folder that contains voice-flow.exe.
    - Source checkout: the repo root (two levels above this file).
    """
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _user_config_dir() -> Path:
    """Per-user config dir for the standalone EXE.

    Windows: %APPDATA%\\voice-flow
    Other:   ~/.voice-flow
    """
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "voice-flow"
    return Path.home() / ".voice-flow"


PROJECT_ROOT = _project_root()
USER_CONFIG_DIR = _user_config_dir()


def _candidate_env_files() -> list[Path]:
    """Ordered list of .env candidates. First existing file wins.

    1. Next to the executable / in the repo root  → easiest for source users
    2. %APPDATA%\\voice-flow\\.env                  → written by the first-run wizard
    """
    return [PROJECT_ROOT / ".env", USER_CONFIG_DIR / ".env"]


def _candidate_context_files() -> list[Path]:
    """Same lookup order as .env, but for context.txt."""
    return [PROJECT_ROOT / "context.txt", USER_CONFIG_DIR / "context.txt"]


def find_env_file() -> Path | None:
    """First .env that exists, or None if no candidate is present."""
    for p in _candidate_env_files():
        if p.exists():
            return p
    return None


def find_context_file() -> Path | None:
    """First context.txt that exists, or None."""
    for p in _candidate_context_files():
        if p.exists():
            return p
    return None


# Backwards-compatible constants — point at the *primary* (repo-root) location.
# Code that needs runtime lookup uses find_env_file()/find_context_file().
ENV_FILE = PROJECT_ROOT / ".env"
CONTEXT_FILE = PROJECT_ROOT / "context.txt"


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


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off", ""}


def _parse_bool_env(name: str, default: bool = False) -> bool:
    """Strict bool parser: accepts only well-known truthy/falsy strings."""
    raw = os.getenv(name)
    if raw is None:
        return default
    val = raw.strip().lower()
    if val in _TRUE_VALUES:
        return True
    if val in _FALSE_VALUES:
        return False
    log.warning(
        "Env var %s=%r is not a recognized boolean — ignoring (default %s).",
        name, raw, default,
    )
    return default


def load_context() -> str:
    path = find_context_file()
    if path is None:
        return ""
    return path.read_text(encoding="utf-8").strip()


def load_config(overrides: dict | None = None) -> Config:
    env_path = find_env_file()
    if env_path is not None:
        load_dotenv(env_path)

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        candidates = "\n  - ".join(str(p) for p in _candidate_env_files())
        raise RuntimeError(
            "OPENAI_API_KEY missing.\n\n"
            "Create a .env file with OPENAI_API_KEY=sk-... at one of:\n"
            f"  - {candidates}\n\n"
            "Or set the OPENAI_API_KEY environment variable."
        )

    device_env = os.getenv("VOICE_FLOW_AUDIO_DEVICE")
    audio_device: int | None = None
    if device_env:
        try:
            audio_device = int(device_env)
        except ValueError:
            log.warning(
                "VOICE_FLOW_AUDIO_DEVICE=%r is not a number — falling back to default mic.",
                device_env,
            )
            audio_device = None

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
        enable_cleanup=_parse_bool_env("VOICE_FLOW_ENABLE_CLEANUP", default=False),
        context=load_context(),
    )

    if overrides:
        cfg = replace(cfg, **overrides)

    return cfg
