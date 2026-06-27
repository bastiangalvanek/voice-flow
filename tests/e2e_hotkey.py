"""E2E-Test: simuliert F8 press/release WAEHREND Voice Flow laeuft.

Verifiziert Pipeline-Path:
  F8 press → on_hotkey_press → state RECORDING + audio_mute.mute
  F8 release → on_hotkey_release → state PROCESSING → whisper → paste

KEINE echte Sprache (kein Mikro-Audio injectable), Whisper wird auf der echten
ambient-Audio aus dem Mikro transkribieren ODER "Recording too short" zurueckgeben.

Erfolgs-Kriterium: Log enthaelt 'REC ▶ hotkey=F8' und 'Recording stopped' nach simulierten
press/release Events.

Usage: aus voice-flow root: .venv/Scripts/python.exe tests/e2e_hotkey.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def main() -> int:
    log_file = Path.home() / ".voice-flow" / "logs" / "voice-flow.log"
    if not log_file.exists():
        print("FEHLER: Log-File fehlt — Voice Flow nie gestartet?")
        return 1

    # 1) Marker-Position im Log VOR dem Test
    log_size_before = log_file.stat().st_size
    print(f"Log-Position vor Test: {log_size_before} bytes")

    # 2) Voice Flow muss laufen — check via singleton port
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from voice_flow.singleton import SingletonLock

    if SingletonLock.send_command("ping"):
        print("Voice Flow laeuft (IPC ping OK).")
    else:
        print("FEHLER: Voice Flow laeuft NICHT — bitte zuerst starten.")
        return 2

    # 3) Simuliere F8 press → 1.2s halten → release
    import keyboard
    print("Simuliere F8 press ...")
    keyboard.press("f8")
    time.sleep(1.2)
    print("Simuliere F8 release ...")
    keyboard.release("f8")

    # 4) Warte bis Pipeline durch ist (max 10s)
    print("Warte auf Pipeline (max 10s) ...")
    time.sleep(8)

    # 5) Log-Diff lesen
    with open(log_file, "r", encoding="utf-8") as f:
        f.seek(log_size_before)
        new_log = f.read()

    print("\n=== Neue Log-Eintraege (ASCII-safe) ===")
    print(new_log.encode("ascii", errors="replace").decode("ascii"))

    # 6) Assertions
    checks = [
        ("hotkey=F8", "F8-Press wurde empfangen"),
        ("Recording stopped", "Recorder stoppte sauber"),
    ]
    fails = []
    for needle, label in checks:
        if needle in new_log:
            print(f"  [OK]   {label}")
        else:
            print(f"  [FAIL] {label} (gesucht: {needle!r})")
            fails.append(label)

    if fails:
        print(f"\nFEHLER: {len(fails)} checks fehlgeschlagen")
        return 3
    print("\nOK alle E2E-checks bestanden — F8 funktioniert.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
