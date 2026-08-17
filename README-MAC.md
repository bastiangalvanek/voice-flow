# Voice Flow auf dem Mac

Portierung vom Windows-Stand, 13.08.2026. Der Windows-Pfad ist unverändert —
alle Änderungen hängen an `sys.platform == "darwin"`.

## Starten

```bash
./voice-flow.sh                # normal
./voice-flow.sh --verbose      # mit Debug-Ausgabe
./voice-flow.sh --list-devices # Mikrofone auflisten
```

Umgebung liegt in `.venv` (Python 3.12.13 über `uv`, ohne sudo installiert).

## Rechte, die du einmalig erteilen musst

macOS liefert globale Tastenereignisse nur an freigegebene Programme. Ohne das
startet Voice Flow zwar, **F8 bleibt aber stumm**. Im Log steht dann:

```
This process is not trusted! Input event monitoring will not be possible
until it is added to accessibility clients.
```

Systemeinstellungen → Datenschutz & Sicherheit →
* **Bedienungshilfen** → Terminal (bzw. das startende Programm) hinzufügen und aktivieren
* **Mikrofon** → dasselbe

Danach Voice Flow neu starten.

## Was geändert wurde

| Datei | Änderung | Warum |
|---|---|---|
| `_keyboard_mac.py` | **neu** | Ersatz für die `keyboard`-Bibliothek auf Basis von pynput. `import keyboard` bringt auf macOS den Prozess mit einer CoreFoundation-Assertion um (`__CFDataValidateRange`). Bildet nach: `send`, `on_press_key`, `on_release_key`, `add_hotkey`, `is_pressed`, `unhook_all`. |
| `paste.py` | Import plattformabhängig | `keyboard.send("ctrl+v")` — der Shim dreht ctrl→cmd, sonst passiert unter macOS nichts. |
| `cli.py` | Import plattformabhängig | Hotkey-Registrierung. |
| `tests/test_win_integration.py` | `skipif` ergänzt | Der Test prüft Windows-Shell/COM. Die Datei nutzte das Muster bei einem anderen Test bereits, hier fehlte es. |
| `requirements.txt` | `soundfile`, `pynput` ergänzt | `soundfile` stand nur in `pyproject.toml` — ohne sie gibt `to_opus()` immer `None` zurück und es wird unkomprimiertes WAV hochgeladen. |
| `overlay_qt.py` | Qt-Aufbau vom Thread getrennt | `_run_qt(run_loop=False)` baut Qt nur auf; die Ereignisschleife startet `exec_main_loop()` im Haupt-Thread. AppKit erlaubt GUI-Objekte nur dort — im Thread brach der Start mit `NSException` ab. |
| `cli.py` | Parkstelle ersetzt | Statt `quit_event.wait()` läuft auf macOS die Qt-Schleife im Haupt-Thread; ein QTimer pollt `quit_event` und beendet sie. Ohne Overlay bleibt es beim klassischen Parken. |

## Stand — gemessen, nicht geschätzt

**Läuft:**
- 36/36 Module importieren sauber
- Testsuite: **119 grün, 2 übersprungen, 0 rot**
- Audio: Core Audio erkannt, `MacBook Air-Mikrofon` als Eingang
- Opus-Kompression: libsndfile 1.2.2 mit OGG/OPUS-Unterstützung
- App startet mit `--no-tray --no-overlay` und meldet „Voice Flow bereit"
- `audio_mute` (pycaw/Windows) degradiert sauber statt zu crashen

- **Qt-Oberfläche läuft** — Overlay, Tray und Logo starten sauber, kein Crash.
  Voller Start (`--verbose`, ohne Flags) getestet.

**Nicht getestet:**
- Der komplette Diktat-Durchlauf F8 → Aufnahme → Whisper → Einfügen. Dafür
  fehlt die Bedienungshilfen-Freigabe, die nur du erteilen kannst.
- `audio_mute` auf macOS (stummschalten während der Aufnahme) — auf Windows
  über pycaw gelöst, hier gibt es keine Entsprechung. Aktuell abgeschaltet.
