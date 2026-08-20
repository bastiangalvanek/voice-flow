from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time

if sys.platform == "darwin":
    # Die `keyboard`-Bibliothek stirbt auf macOS schon beim Import.
    from voice_flow import _keyboard_mac as keyboard
else:
    import keyboard

from voice_flow.app import VoiceFlowApp
from voice_flow.config import Config, load_config
from voice_flow.gui_errors import show_error
from voice_flow.logging_setup import setup_logging
from voice_flow.recording_storage import (
    RECORDINGS_DIR,
    cleanup_old_recordings,
    list_pending_with_audio,
)
from voice_flow.singleton import SingletonLock

log = logging.getLogger("voice_flow.cli")


# ── Hotkey-Helper ───────────────────────────────────────────────────────

# Aliases fuer User-Convenience (config kann "win" oder "windows" haben)
_KEY_ALIASES = {
    "win": "windows",
    "cmd": "windows",
    "meta": "windows",
    "super": "windows",
}

_KEY_DISPLAY_DE = {
    "ctrl": "Strg",
    "windows": "Win",
    "win": "Win",
    "alt": "Alt",
    "shift": "Shift",
    "space": "Leer",
    "enter": "Enter",
    "esc": "Esc",
}


def _normalize_key(name: str) -> str:
    n = name.lower().strip()
    return _KEY_ALIASES.get(n, n)


def format_hotkey_display(hotkey: str) -> str:
    """Macht aus 'ctrl+windows' → 'Strg + Win'."""
    parts = hotkey.split("+")
    return " + ".join(_KEY_DISPLAY_DE.get(_normalize_key(p), p.upper()) for p in parts)


# Aggregierte Modifier → physikalische Tasten
# (keyboard.on_press_key('windows', ...) feuert NICHT auf left/right windows direkt)
_PHYSICAL_KEYS_FOR = {
    "ctrl": ["left ctrl", "right ctrl"],
    "windows": ["left windows", "right windows"],
    "shift": ["left shift", "right shift"],
    "alt": ["left alt", "right alt"],
}


def _setup_hold_hotkey(hotkey: str, on_press, on_release) -> None:
    """Registriert Press/Release-Detection fuer single keys ODER hold-combos.

    BUG-Fix (17.05): on_press_key("windows", ...) feuert nicht direkt — wir
    muessen auf BEIDE physikalische Varianten (left windows + right windows)
    hooken. Gleiche Logik fuer ctrl/shift/alt.
    """
    parts = [_normalize_key(p) for p in hotkey.split("+")]

    if len(parts) == 1:
        # Single-Key (F8 etc.) → direkter hook
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

    # Hooke auf ALLE physikalischen Variants jeder Modifier-Taste
    physical_keys = []
    for p in parts:
        physical_keys.extend(_PHYSICAL_KEYS_FOR.get(p, [p]))

    log.info("Hotkey-Combo hooks: %s → physical keys %s", parts, physical_keys)

    for key in physical_keys:
        keyboard.on_press_key(key, check_combo, suppress=False)
        keyboard.on_release_key(key, check_combo, suppress=False)


def _setup_toggle_hotkey(hotkey: str, on_toggle) -> None:
    """Toggle-Mode: 1x druecken = Start, nochmal druecken = Stop.

    27.06 Bastian: Edge-getriggert auf den Tastendruck statt auf Typematic-
    Repeats. 'armed' wird beim ersten KEY_DOWN auf False gesetzt und erst beim
    echten KEY_UP wieder True. Damit feuern Repeats einer GEHALTENEN Taste NICHT
    erneut (kein versehentliches Stop nach 250ms), zwei BEWUSSTE Druecke aber
    schon (auch schnell hintereinander). Robuster als ein Zeit-Debounce, der
    schnelle Stops verschlucken wuerde.
    """
    parts = [_normalize_key(p) for p in hotkey.split("+")]

    if len(parts) == 1:
        keys = _PHYSICAL_KEYS_FOR.get(parts[0], [parts[0]])
        state = {"armed": True}

        def on_press(_e) -> None:
            if state["armed"]:
                state["armed"] = False
                on_toggle()

        def on_release(_e) -> None:
            state["armed"] = True

        for key in keys:
            keyboard.on_press_key(key, on_press, suppress=False)
            keyboard.on_release_key(key, on_release, suppress=False)
        return

    # Combo-Hotkey (selten im Toggle-Mode): add_hotkey + App-Backstop-Debounce.
    keyboard.add_hotkey(hotkey, on_toggle, suppress=False)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="voice-flow",
        description="Diktat-Tool. Hotkey druecken = Aufnahme an, nochmal = aus (Mac: F5, Windows: F8). Text landet im aktiven Fenster.",
    )
    p.add_argument("--hotkey", help="Push-to-Talk-Taste (Default: Mac f5 / Windows f8, oder VOICE_FLOW_HOTKEY env)")
    p.add_argument("--no-tray", action="store_true", help="Tray-Icon deaktivieren")
    p.add_argument(
        "--no-overlay",
        action="store_true",
        help="Schwebende Recording-Pille (Wispr-Style) deaktivieren",
    )
    p.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Claude-Cleanup ueberspringen, nur Whisper-Output paste'n",
    )
    p.add_argument("--no-sound", action="store_true", help="Audio-Feedback (Beeps) deaktivieren")
    p.add_argument("--verbose", "-v", action="store_true", help="Debug-Logging in Console")
    p.add_argument(
        "--device",
        type=int,
        default=None,
        help="Audio-Eingabe-Geraete-Index (Default: System-Default; siehe --list-devices)",
    )
    p.add_argument(
        "--list-devices",
        action="store_true",
        help="Audio-Eingabe-Geraete listen und beenden",
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
    hk = format_hotkey_display(cfg.hotkey)
    hk_hint = f"{hk} = Start/Stop" if cfg.hotkey_mode == "toggle" else f"{hk} halten"
    print(line)
    print(" Voice Flow — Galvanek Edition")
    print(line)
    print(f"  Hotkey        {hk_hint}")
    print(f"  Quit          {format_hotkey_display(cfg.quit_hotkey)}")
    print(f"  Sprache       {cfg.language}")
    print(f"  Whisper       {cfg.whisper_model}")
    print(f"  Cleanup       {cfg.cleanup_model if cfg.cleanup_available else 'AUS'}")
    print(f"  Kontext       {len(cfg.context)} Zeichen")
    print(f"  Audio-Device  {cfg.audio_device if cfg.audio_device is not None else 'System-Default'}")
    print(f"  Tray          {'an' if cfg.enable_tray else 'aus'}")
    print(f"  Overlay       {'an' if cfg.enable_overlay else 'aus'}")
    print(f"  Sound         {'an' if cfg.enable_sound else 'aus'}")
    print(f"  Log           {log_file}")
    print(line)
    if cfg.hotkey_mode == "toggle":
        print(f" Cursor irgendwo platzieren, {hk} druecken, sprechen, {hk} zum Senden.")
    else:
        print(f" Cursor irgendwo platzieren, {hk} halten, sprechen, loslassen.")
    print()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # 27.06 Bastian: eigene AppUserModelID -> Windows gruppiert den Taskleisten-Button
    # NICHT unter pythonw.exe und zeigt das Fenster-Icon (Flocke) statt des Python-Icons.
    # Muss VOR der ersten Fenster-Erzeugung passieren. Identitaet = SSoT in
    # win_integration; derselbe Wert muss auf dem angehefteten Shortcut stehen.
    from voice_flow.win_integration import set_process_aumid

    set_process_aumid()

    if args.list_devices:
        return list_devices()

    log_file = setup_logging(verbose=args.verbose)

    # Singleton-Lock: verhindert dass Doppelklick auf Desktop-Icon
    # eine zweite Instanz startet. Zweiter Klick schickt stattdessen
    # ein "show_ready" an die laufende Instanz → grüne Pille erscheint
    # nochmal, der User weiss "ah, läuft schon."
    lock = SingletonLock()
    if not lock.acquire():
        log.info("Voice Flow laeuft bereits — pinge erste Instanz fuer show_ready.")
        if SingletonLock.send_command("show_ready"):
            # IPC erfolgreich — User sieht gleich die Pille, keine MessageBox noetig
            log.info("show_ready erfolgreich an erste Instanz uebermittelt.")
            return 0
        # IPC fehlgeschlagen — Fallback zur MessageBox
        log.error("IPC zur ersten Instanz fehlgeschlagen.")
        show_error(
            "Voice Flow",
            "Voice Flow laeuft bereits.\n\nFalls du das Tray-Icon nicht siehst,\n"
            "klicke auf den ^-Pfeil in der Tray-Leiste (links der Uhr).",
        )
        return 1

    try:
        cfg = load_config(_build_overrides(args))
    except RuntimeError as ex:
        log.error("%s", ex)
        show_error(
            "Voice Flow — Konfiguration unvollstaendig",
            f"{ex}\n\nLog: {log_file}",
        )
        lock.release()
        return 2

    _print_banner(cfg, log_file)

    # Recording-Retention (Alter + Groessen-Deckel), dann pending listen
    try:
        cleanup_old_recordings()
        pending = list_pending_with_audio()
        if pending:
            log.warning(
                "%d Recording(s) liegen in %s — Retry: python -m voice_flow.recover",
                len(pending), RECORDINGS_DIR,
            )
    except Exception as ex:
        log.debug("Recording-Storage cleanup error (ignoriert): %s", ex)

    app = VoiceFlowApp(cfg)

    # Tray + Quit-Handler sind verschraenkt: quit_handler muss tray.stop() koennen,
    # aber tray.ctor braucht quit_handler. Loesung: Holder-Dict, late-bound.
    holder: dict = {"tray": None, "quit_initiated": False}
    # Event signalisiert main thread dass er aus keyboard.wait() raus soll
    quit_event = threading.Event()
    # Quit kann aus Tray-Thread UND Qt-Thread (Fenster-X) gleichzeitig kommen —
    # Lock macht das Check-and-Set wirklich atomar (sonst doppelter Teardown).
    quit_lock = threading.Lock()

    def quit_handler() -> None:
        # NUR signalisieren — KEIN Teardown hier. Quit kann aus dem keyboard-,
        # Qt- (Fenster-X) oder Tray-Thread kommen; Cross-Thread-Teardown (COM-
        # Audio-Unmute, Qt, pystray aus dem falschen Thread) kann DEADLOCKEN —
        # genau das hat den Zombie erzeugt (Log blieb bei "shutdown initiated"
        # haengen, Port blieb belegt). Der Main-Thread raeumt mit korrekter
        # Thread-Affinitaet auf; ein Watchdog garantiert den Prozess-Tod.
        with quit_lock:
            if holder["quit_initiated"]:
                return
            holder["quit_initiated"] = True
        log.info("Quit angefordert.")

        def _hard_exit() -> None:
            # KEIN Logging hier: der Logging-Lock kann beim Shutdown gehalten
            # sein -> log.* wuerde den Watchdog selbst deadlocken. Nur os._exit.
            time.sleep(2.0)
            os._exit(0)

        threading.Thread(target=_hard_exit, daemon=True, name="quit-watchdog").start()
        quit_event.set()

    # Control-Fenster: X / Taskleiste-Rechtsklick-Schliessen = derselbe saubere Quit.
    # Erst Handler verdrahten, DANN zeigen — sonst Race (Schliessen vor verdrahtetem
    # Quit wuerde die App verwaisen lassen).
    if app.overlay is not None:
        app.overlay.set_quit_handler(quit_handler)
        app.overlay.show_control_window()

    if cfg.enable_tray:
        try:
            from voice_flow.tray import TrayIcon

            tray = TrayIcon(on_quit=quit_handler)
            holder["tray"] = tray
            app.tray = tray
            tray.run_detached()
            app._tray_set("idle")  # initial state setzen
        except ImportError as ex:
            log.warning("pystray/Pillow fehlt (%s) — laufe ohne Tray.", ex)
        except Exception as ex:
            log.warning("Tray-Start fehlgeschlagen: %s — laufe ohne Tray.", ex)

    # Hotkey kann ein Single-Key sein ("f8") ODER eine Hold-Combo ("ctrl+windows").
    # keyboard.on_press_key arbeitet nur mit single keys — fuer Combos brauchen wir
    # eigene "alle Tasten gedrueckt?"-Detection.
    if cfg.hotkey_mode == "toggle":
        _setup_toggle_hotkey(cfg.hotkey, app.on_hotkey_toggle)
    else:
        _setup_hold_hotkey(cfg.hotkey, app.on_hotkey_press, app.on_hotkey_release)
    # 27.06 Bastian: F7 = Screenshot des Monitors unter der Maus in den Session-Bucket.
    keyboard.add_hotkey(cfg.screenshot_hotkey, app.on_screenshot_hotkey, suppress=False)
    # 27.06 Bastian: F6 = Loom-Zeichen-Overlay, dann Screenshot mit Markierungen.
    keyboard.add_hotkey(cfg.annotate_hotkey, app.on_annotate_hotkey, suppress=False)
    keyboard.add_hotkey(cfg.quit_hotkey, quit_handler)
    # ESC schliesst die Zeichen-Ebene. Noetig, seit die Ebene den Fokus nicht
    # mehr an sich reisst (sonst kam das minimierte Fenster hoch, 19.08.).
    keyboard.add_hotkey("esc", app.on_escape, suppress=False)
    # Letztes Diktat noch einmal einfuegen (Text, dann Bilder).
    keyboard.add_hotkey(cfg.repaste_hotkey, app.on_repaste_hotkey, suppress=False)
    if sys.platform == "darwin":
        # Einmal Cmd+V = ganze Kaskade (nur solange die Zwischenablage noch
        # unsere Bilder traegt — sonst bleibt Cmd+V das normale Einfuegen).
        keyboard.set_cmd_v_hook(app.on_cmd_v)

    log.info(
        "Bereit. %s %s zum Diktieren, %s zum Beenden.",
        format_hotkey_display(cfg.hotkey),
        "druecken (Start/Stop)" if cfg.hotkey_mode == "toggle" else "halten",
        format_hotkey_display(cfg.quit_hotkey),
    )

    # IPC-Handler: zweite Instanz schickt "show_ready" → erste Instanz zeigt Pille
    def handle_ipc(cmd: str) -> None:
        cmd = cmd.strip().lower()
        if cmd == "show_ready":
            app.show_ready()
        elif cmd == "ping":
            pass  # nur ACK, kein UI
        else:
            log.warning("Unbekannter IPC-Command: %r", cmd)

    lock.set_command_handler(handle_ipc)

    # macOS: Berechtigungen AKTIV anfragen. pynput loest den Dialog nie selbst
    # aus — ohne das hier bleibt F8 fuer immer stumm und niemand sieht warum.
    if sys.platform == "darwin":
        from voice_flow import darwin_permissions

        def _notify_perm(msg: str) -> None:
            if app.overlay is not None and getattr(app.overlay, "available", False):
                app.overlay.show_info("Bedienungshilfen fehlen — Einstellungen geoeffnet", 8000)
            print(f"\n  !!! {msg}\n")

        darwin_permissions.ensure_all(notify=_notify_perm)

    # Sichtbare + hoerbare Startup-Notice — sonst weiss Bastian nicht dass es laeuft
    # (pythonw hat keine Konsole, Tray-Icon ist oft in Windows-Overflow-Menu versteckt).
    app.show_ready()

    try:
        # NICHT keyboard.wait(): das macht intern `while True: sleep(1e6)` und
        # kehrt bei keyboard.unhook_all() NICHT zurueck. Hotkeys laufen in
        # keyboards eigenem (daemon) Listener-Thread; dieser Main-Thread parkt
        # nur, bis quit_handler quit_event setzt.
        #
        # macOS: AppKit verlangt die Qt-Schleife im Haupt-Thread. Statt hier zu
        # parken, laeuft sie hier — beendet wird sie per QTimer, sobald
        # quit_event gesetzt ist. Ohne Overlay (--no-overlay) bleibt es beim
        # klassischen Parken.
        _ov = getattr(app, "overlay", None)
        if sys.platform == "darwin" and _ov is not None and getattr(_ov, "available", False):
            _ov.exec_main_loop(quit_event)
        else:
            quit_event.wait()
    except KeyboardInterrupt:
        log.info("KeyboardInterrupt — beende.")
        quit_handler()  # Watchdog armen + Event setzen
    finally:
        # Teardown im MAIN-Thread (verlaessliche Thread-/COM-Affinitaet — im
        # Callback-Thread deadlockte der COM-Unmute). Reihenfolge: Audio-Unmute
        # zuerst (sonst bleibt System stumm), dann UI/Hooks, dann Port. Falls
        # hier doch etwas haengt, killt der quit-watchdog den Prozess nach 2s.
        t = holder["tray"]
        if t:
            try:
                t.stop()
            except Exception:
                pass
        try:
            app.shutdown()  # Recorder stoppen, Audio unmuten, Overlay schliessen
        except Exception as ex:
            log.debug("app.shutdown error: %s", ex)
        try:
            keyboard.unhook_all()
        except Exception as ex:
            log.debug("keyboard.unhook_all error: %s", ex)
        lock.release()  # Singleton-Port freigeben — sonst Zombie
        log.info("Voice Flow beendet.")
        logging.shutdown()  # File-Handler flushen vor hartem Exit
        # Garantierter Prozess-Tod: pystray/keyboard koennen Non-Daemon-Threads
        # hinterlassen, die den Prozess sonst am Leben halten. Hart raus.
        os._exit(0)

    return 0


if __name__ == "__main__":
    sys.exit(main())
