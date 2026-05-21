from __future__ import annotations

import argparse
import logging
import sys
import threading

import keyboard

from voice_flow.app import VoiceFlowApp
from voice_flow.config import Config, load_config
from voice_flow.gui_errors import show_error
from voice_flow.logging_setup import setup_logging
from voice_flow.recording_storage import (
    RECORDINGS_DIR,
    cleanup_old_recordings,
    list_pending_recordings,
)
from voice_flow.singleton import SingletonLock

log = logging.getLogger("voice_flow.cli")


# ── Hotkey helpers ──────────────────────────────────────────────────────

_KEY_ALIASES = {
    "win": "windows",
    "cmd": "windows",
    "meta": "windows",
    "super": "windows",
}

_KEY_DISPLAY = {
    "ctrl": "Ctrl",
    "windows": "Win",
    "win": "Win",
    "alt": "Alt",
    "shift": "Shift",
    "space": "Space",
    "enter": "Enter",
    "esc": "Esc",
}


def _normalize_key(name: str) -> str:
    n = name.lower().strip()
    return _KEY_ALIASES.get(n, n)


def format_hotkey_display(hotkey: str) -> str:
    """Turn 'ctrl+windows' into 'Ctrl + Win'."""
    parts = hotkey.split("+")
    return " + ".join(_KEY_DISPLAY.get(_normalize_key(p), p.upper()) for p in parts)


# Aggregated modifiers → physical keys
# (keyboard.on_press_key('windows', ...) does NOT fire on left/right windows directly)
_PHYSICAL_KEYS_FOR = {
    "ctrl": ["left ctrl", "right ctrl"],
    "windows": ["left windows", "right windows"],
    "shift": ["left shift", "right shift"],
    "alt": ["left alt", "right alt"],
}


def _setup_hold_hotkey(hotkey: str, on_press, on_release) -> None:
    """Register press/release detection for single keys OR hold-combos.

    on_press_key("windows", ...) doesn't fire directly — we must hook BOTH
    physical variants (left + right). Same for ctrl/shift/alt.
    """
    parts = [_normalize_key(p) for p in hotkey.split("+")]

    if len(parts) == 1:
        # Single key (F8 etc.) → direct hook
        keys = _PHYSICAL_KEYS_FOR.get(parts[0], [parts[0]])
        for key in keys:
            keyboard.on_press_key(key, lambda e: on_press(), suppress=False)
            keyboard.on_release_key(key, lambda e: on_release(), suppress=False)
        return

    state = {"active": False}

    def check_combo(event) -> None:
        all_pressed = all(keyboard.is_pressed(p) for p in parts)
        if all_pressed and not state["active"]:
            state["active"] = True
            log.debug("Hotkey combo PRESSED: %s", parts)
            on_press()
        elif not all_pressed and state["active"]:
            state["active"] = False
            log.debug("Hotkey combo RELEASED: %s", parts)
            on_release()

    physical_keys = []
    for p in parts:
        physical_keys.extend(_PHYSICAL_KEYS_FOR.get(p, [p]))

    log.info("Hotkey combo hooks: %s → physical keys %s", parts, physical_keys)

    for key in physical_keys:
        keyboard.on_press_key(key, check_combo, suppress=False)
        keyboard.on_release_key(key, check_combo, suppress=False)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="voice-flow",
        description="Push-to-talk dictation. Hold F8, speak, release — text lands in the active window.",
    )
    p.add_argument("--hotkey", help="Push-to-talk key (default: f8 or VOICE_FLOW_HOTKEY env)")
    p.add_argument("--no-tray", action="store_true", help="Disable tray icon")
    p.add_argument(
        "--no-overlay",
        action="store_true",
        help="Disable the floating recording pill",
    )
    p.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Skip Claude cleanup, paste raw Whisper output",
    )
    p.add_argument("--no-sound", action="store_true", help="Disable audio feedback (beeps)")
    p.add_argument("--verbose", "-v", action="store_true", help="Debug logging in console")
    p.add_argument(
        "--device",
        type=int,
        default=None,
        help="Audio input device index (default: system; see --list-devices)",
    )
    p.add_argument(
        "--list-devices",
        action="store_true",
        help="List audio input devices and exit",
    )
    return p.parse_args(argv)


def list_devices() -> int:
    import sounddevice as sd

    print(sd.query_devices())
    return 0


def _build_overrides(args: argparse.Namespace) -> dict:
    overrides: dict = {}
    if args.hotkey:
        overrides["hotkey"] = args.hotkey
    if args.no_tray:
        overrides["enable_tray"] = False
    if args.no_overlay:
        overrides["enable_overlay"] = False
    if args.no_cleanup:
        overrides["enable_cleanup"] = False
    if args.no_sound:
        overrides["enable_sound"] = False
    if args.verbose:
        overrides["verbose"] = True
    if args.device is not None:
        overrides["audio_device"] = args.device
    return overrides


def _print_banner(cfg: Config, log_file) -> None:
    line = "=" * 66
    print(line)
    print(" Voice Flow")
    print(line)
    print(f"  Hotkey        hold {format_hotkey_display(cfg.hotkey)}")
    print(f"  Quit          {format_hotkey_display(cfg.quit_hotkey)}")
    print(f"  Language      {cfg.language}")
    print(f"  Whisper       {cfg.whisper_model}")
    print(f"  Cleanup       {cfg.cleanup_model if cfg.cleanup_available else 'OFF'}")
    print(f"  Context       {len(cfg.context)} chars")
    print(f"  Audio device  {cfg.audio_device if cfg.audio_device is not None else 'system default'}")
    print(f"  Tray          {'on' if cfg.enable_tray else 'off'}")
    print(f"  Overlay       {'on' if cfg.enable_overlay else 'off'}")
    print(f"  Sound         {'on' if cfg.enable_sound else 'off'}")
    print(f"  Log           {log_file}")
    print(line)
    print(" Place cursor anywhere, hold F8, speak, release.")
    print()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.list_devices:
        return list_devices()

    log_file = setup_logging(verbose=args.verbose)

    # Singleton lock: prevents a second instance starting. A second click
    # sends "show_ready" to the running instance instead.
    lock = SingletonLock()
    if not lock.acquire():
        log.info("Voice Flow already running — pinging first instance for show_ready.")
        if SingletonLock.send_command("show_ready"):
            log.info("show_ready delivered to first instance.")
            return 0
        log.error("IPC to first instance failed.")
        show_error(
            "Voice Flow",
            "Voice Flow is already running.\n\nIf you can't see the tray icon,\n"
            "click the ^ in the tray area (left of the clock).",
        )
        return 1

    try:
        cfg = load_config(_build_overrides(args))
    except RuntimeError as ex:
        log.error("%s", ex)
        show_error(
            "Voice Flow — configuration incomplete",
            f"{ex}\n\nLog: {log_file}",
        )
        lock.release()
        return 2

    _print_banner(cfg, log_file)

    try:
        cleanup_old_recordings()
        pending = list_pending_recordings()
        if pending:
            log.warning(
                "%d recording(s) sitting in %s — earlier pipeline failures?",
                len(pending), RECORDINGS_DIR,
            )
    except Exception as ex:
        log.debug("Recording storage cleanup error (ignored): %s", ex)

    app = VoiceFlowApp(cfg)

    # Tray + quit handler are intertwined: quit_handler must call tray.stop(),
    # but tray.ctor needs quit_handler. Solution: holder dict, late-bound.
    holder: dict = {"tray": None, "quit_initiated": False}
    quit_event = threading.Event()

    def quit_handler() -> None:
        # Idempotent: repeated clicks on the quit menu must not crash.
        if holder["quit_initiated"]:
            return
        holder["quit_initiated"] = True
        log.info("Quit requested.")
        t = holder["tray"]
        if t:
            try:
                t.stop()
            except Exception:
                pass
        try:
            app.shutdown()
        except Exception as ex:
            log.debug("app.shutdown error: %s", ex)
        try:
            keyboard.unhook_all()
        except Exception as ex:
            log.debug("keyboard.unhook_all error: %s", ex)
        quit_event.set()

    if cfg.enable_tray:
        try:
            from voice_flow.tray import TrayIcon

            tray = TrayIcon(on_quit=quit_handler)
            holder["tray"] = tray
            app.tray = tray
            tray.run_detached()
            app._tray_set("idle")
        except ImportError as ex:
            log.warning("pystray/Pillow missing (%s) — running without tray.", ex)
        except Exception as ex:
            log.warning("Tray start failed: %s — running without tray.", ex)

    _setup_hold_hotkey(cfg.hotkey, app.on_hotkey_press, app.on_hotkey_release)
    keyboard.add_hotkey(cfg.quit_hotkey, quit_handler)

    log.info(
        "Ready. Hold %s to dictate, press %s to quit.",
        format_hotkey_display(cfg.hotkey),
        format_hotkey_display(cfg.quit_hotkey),
    )

    def handle_ipc(cmd: str) -> None:
        cmd = cmd.strip().lower()
        if cmd == "show_ready":
            app.show_ready()
        elif cmd == "ping":
            pass
        else:
            log.warning("Unknown IPC command: %r", cmd)

    lock.set_command_handler(handle_ipc)

    # Visible + audible startup notice — pythonw has no console, tray icon may
    # be hidden in the Windows overflow menu.
    app.show_ready()

    try:
        keyboard.wait()
    except KeyboardInterrupt:
        log.info("KeyboardInterrupt — exiting.")
    finally:
        if not holder["quit_initiated"]:
            quit_handler()
        quit_event.wait(timeout=1.0)
        lock.release()
        log.info("Voice Flow stopped.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
