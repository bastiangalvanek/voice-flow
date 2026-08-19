# Voice Flow — Galvanek Edition

Dictation tool for **macOS and Windows**. Press a key, speak, press again — the
text lands wherever your cursor is (Gmail, ClickUp, Word, browser, Claude Code,
anything). Screenshots come along: as file paths for Claude Code, or as real
images for the web.

Built on OpenAI Whisper for transcription, with an optional Claude Haiku 4.5
cleanup pass.

---

## Download

No Python, no terminal, no setup — both platforms ship as a finished installer:

**[→ Download the latest version](https://github.com/bastiangalvanek/voice-flow/releases/latest)**

| Platform | File | Guide |
|---|---|---|
| **macOS** (Apple Silicon) | `VoiceFlow-vX.Y.Z-macOS.dmg` | **[macOS setup](docs/INSTALL-MACOS.md)** |
| **Windows 10/11** | `VoiceFlow-X.Y.Z-Setup.exe` | **[Windows setup](docs/INSTALL-WINDOWS.md)** |
| Windows, no installer | `VoiceFlow-X.Y.Z-Windows.zip` | unpack, run `VoiceFlow.exe` |

**[→ Complete feature reference](docs/FEATURES.md)** — every feature explained in
detail: screenshot weaving, target modes, annotation, the data-loss safety net,
long-recording chunking, and the full configuration reference.

No download contains an API key — you add your own (one line, covered in both
setup guides).

### Keys

| macOS | Windows | Action |
|---|---|---|
| F5 | F8 | Start / stop recording |
| F3 | F7 | Screenshot of the monitor under the mouse |
| F6 | F6 | Annotate: draw, then capture |

### How releases are verified

Every release runs the full test suite on both platforms. On Windows the
installer is additionally **installed, launched and uninstalled on a real
Windows machine** — if any of that fails, the release never publishes. Not
covered there: how the window *looks*, since the build machine has no screen.
That is checked by hand.

---

## 🚀 Schnellstart fuer Kollegen (ZIP erhalten?)

> Das ZIP enthaelt **keine API-Keys** — du traegst deinen eigenen ein. Sonst ist alles fertig gebrandet (Logo + Icon).

1. **ZIP entpacken** in einen Ordner deiner Wahl (z.B. `Dokumente\voice-flow`).
2. **Python 3.10+** installiert? Falls nicht: [python.org/downloads](https://www.python.org/downloads/) → bei der Installation **"Add Python to PATH"** anhaken.
3. PowerShell im entpackten Ordner oeffnen (Rechtsklick im Ordner → *In Terminal oeffnen*) und ausfuehren:
   ```powershell
   .\install.ps1
   ```
4. Notepad oeffnet automatisch die `.env` → trage deinen **`OPENAI_API_KEY`** ein ([hier holen](https://platform.openai.com/api-keys)), speichern, schliessen.
5. **Doppelklick auf "Voice Flow"** (Desktop). Cursor in ein Textfeld → **F8** druecken/halten, sprechen, fertig.

Stockt etwas? Gib diesen Ordner deiner **Claude-Code**-Session und sag *"installier mir Voice Flow nach README"* — der Rest ist automatisiert.

---

## Installation als richtiges Windows-Programm (empfohlen)

```powershell
# In den entpackten/geklonten voice-flow-Ordner wechseln, dann:
.\install.ps1
```

Das macht:
1. Virtual-Env anlegen + Package installieren
2. `.env` aus Template → Notepad fuer Keys → speichern
3. `voice-flow.ico` generieren (nutzt `logo.png` falls vorhanden, sonst Mikro-Fallback)
4. **Desktop-Shortcut "Voice Flow"** anlegen
5. **Startmenu-Eintrag** anlegen
6. Frage: Autostart bei Windows-Login? J/n

### Eigenes Logo verwenden

Lege einfach `logo.png` (transparenter Hintergrund, quadratisch ideal) in den voice-flow-Ordner und lass `.\install.ps1` erneut laufen — die Shortcuts kriegen automatisch dein Logo, und das Tray-Icon nutzt es ebenfalls (gefaerbt nach Status: grau=idle, rot=rec, orange=processing).

**Danach: Doppelklick auf "Voice Flow" auf dem Desktop = Programm laeuft im Tray.**
Kein PowerShell, kein Konsolen-Fenster, einfach Icon klicken und los.

Deinstallieren: `.\uninstall.ps1` (entfernt nur die Shortcuts; Code + .venv bleiben).

---

## Alternative: nur im Terminal starten

```powershell
.\run.ps1                       # 1-Click venv + start
# oder manuell:
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
Copy-Item .env.example .env
notepad .env
voice-flow                      # mit Konsole + Logs
voice-flow --verbose            # Debug-Modus
```

---

## Nutzung

1. Voice Flow laeuft im Tray (graues Mikro-Icon → idle)
2. Cursor in beliebiges Textfeld
3. **F8 halten** → Icon wird **rot** (Recording), sprich
4. **F8 loslassen** → Icon wird **orange** (Processing), dann **grau** — Text ist eingefuegt
5. Quit: `Ctrl+Shift+Q` oder Rechtsklick auf Tray-Icon → Quit

---

## CLI-Optionen

```powershell
voice-flow                     # Default: Tray + Sound + Cleanup
voice-flow --verbose           # Debug-Logging in Console
voice-flow --no-tray           # ohne Tray-Icon
voice-flow --no-cleanup        # nur Whisper-Output, kein Claude
voice-flow --no-sound          # ohne Beeps
voice-flow --hotkey f9         # andere Push-to-Talk-Taste
voice-flow --device 1          # Mikro-Index (vorher --list-devices)
voice-flow --list-devices      # Mikrofon-Indizes anzeigen
```

---

## Konfiguration via `.env`

| Variable | Default | Zweck |
|---|---|---|
| `OPENAI_API_KEY` | **Pflicht** | OpenAI Whisper |
| `ANTHROPIC_API_KEY` | optional | Wenn gesetzt: Claude-Cleanup aktiv |
| `VOICE_FLOW_HOTKEY` | `f8` | Push-to-Talk-Taste |
| `VOICE_FLOW_LANGUAGE` | `de` | Whisper-Sprache (ISO-Code) |
| `VOICE_FLOW_WHISPER_MODEL` | `whisper-1` | Whisper-Modell |
| `VOICE_FLOW_CLEANUP_MODEL` | `claude-haiku-4-5-20251001` | Cleanup-Modell |
| `VOICE_FLOW_AUDIO_DEVICE` | System-Default | Mikrofon-Index aus `--list-devices` |

CLI-Args ueberschreiben `.env`-Werte.

---

## Custom-Vokabular: `galvanek_context.txt`

Hier stehen Mitarbeiter, Projekte, Fachbegriffe. Wird:
- als **Whisper-Prompt** mitgegeben (erste ~220 Zeichen — hilft Eigennamen zu erkennen)
- als **System-Prompt** fuer Claude-Cleanup verwendet (komplette Datei — fuer harte Korrekturen wie "klick app" → "ClickUp")

Anpassen: einfach Datei editieren, Voice Flow neu starten.

---

## Architektur

```
F8 down ─┐
         ├─ AudioRecorder (sounddevice, 16kHz mono int16)
F8 up   ─┘
                 │
                 ▼
         WAV-Bytes (in memory, kein temp-file)
                 │
                 ▼
         Transcriber  ── OpenAI Whisper API + Retry-Backoff
                 │
                 ▼
         Cleaner      ── Claude Haiku 4.5 + Galvanek-Context (optional)
                 │
                 ▼
         paste_to_active_window  ── Clipboard + Strg+V + Restore
```

### Module

| Datei | Verantwortung |
|---|---|
| `src/voice_flow/config.py` | `.env` + CLI overrides → immutable `Config`-Dataclass |
| `src/voice_flow/audio.py` | `AudioRecorder` — sounddevice Stream, thread-safe |
| `src/voice_flow/transcription.py` | `Transcriber` — OpenAI Whisper Client, 3-fach Retry |
| `src/voice_flow/cleanup.py` | `Cleaner` — Anthropic Claude, 2-fach Retry, Fallback auf Rohtext |
| `src/voice_flow/paste.py` | Clipboard-basiertes Paste mit Restore |
| `src/voice_flow/sound.py` | `winsound.Beep` Feedback (Start/Stop/Error) |
| `src/voice_flow/tray.py` | `pystray` System-Tray mit farbigem Status-Icon |
| `src/voice_flow/app.py` | `VoiceFlowApp` — Controller / State-Machine |
| `src/voice_flow/cli.py` | argparse Entry-Point, wire-up, banner |
| `src/voice_flow/logging_setup.py` | Console + File-Logging (`~/.voice-flow/logs/`) |
| `src/voice_flow/singleton.py` | Port-Lock — verhindert dass Doppelklick zweite Instanz startet |
| `src/voice_flow/gui_errors.py` | tkinter Message-Box fuer Fehler im pythonw-Mode (kein Konsolen-Fenster) |

---

## Tests

```powershell
pip install -e ".[dev]"
pytest
```

Smoke-Tests fuer Config-Loading und Cleanup-Fallback-Verhalten. Audio/Whisper/Claude/Paste sind I/O — manuell testen.

---

## Troubleshooting

| Symptom | Ursache / Fix |
|---|---|
| **F8 reagiert nicht** | PowerShell als Admin starten (`keyboard` lib braucht oft globale Hotkey-Privilege) |
| **Falsches Mikrofon** | `voice-flow --list-devices` → Index merken → `voice-flow --device N` oder `VOICE_FLOW_AUDIO_DEVICE=N` in `.env` |
| **Tray erscheint nicht** | `voice-flow --no-tray --verbose` → Log checken (`~/.voice-flow/logs/voice-flow.log`) |
| **Whisper haut Namen falsch** | Eigennamen in `galvanek_context.txt` ergaenzen, ersten Block ans Anfang stellen (geht als Whisper-Prompt rein) |
| **Cleanup vergewaltigt deinen Stil** | System-Prompt in `src/voice_flow/cleanup.py` `SYSTEM_PROMPT_TEMPLATE` anpassen oder `--no-cleanup` nutzen |
| **Latenz >3s** | Whisper-API dominiert. Lokales Whisper (faster-whisper + CUDA) auf der Roadmap. |
| **Stille Audio-Aufnahme** | Default-Mikro checken (Windows-Sound-Einstellungen), `--list-devices`, ggf. anderes Device setzen |

---

## Roadmap

- [ ] Lokales Whisper (faster-whisper, GPU) als Privacy-Mode
- [ ] Zweiter Hotkey mit Custom-Cleanup-Prompt (z.B. F9 = "schreib in ClickUp-Task-Stil")
- [ ] n8n-Webhook-Hotkey (F10 = diktieren → direkt als ClickUp-Task / Gmail-Draft anlegen)
- [ ] EXE-Build mit PyInstaller fuer Autostart bei Windows-Login
- [ ] GUI-Settings statt `.env`-Editing
- [ ] Streaming-Transcription (sobald OpenAI API es stabil supportet)

---

## Files-Layout

```
apps/tools/voice-flow/
├── src/voice_flow/         # Python-Package (pip install -e .)
│   ├── __init__.py
│   ├── __main__.py         # python -m voice_flow
│   ├── cli.py
│   ├── config.py
│   ├── audio.py
│   ├── transcription.py
│   ├── cleanup.py
│   ├── paste.py
│   ├── sound.py
│   ├── tray.py
│   ├── app.py
│   ├── singleton.py        # Port-Lock gegen Doppel-Start
│   ├── gui_errors.py       # Message-Box bei pythonw-Crash
│   └── logging_setup.py
├── tests/
├── pyproject.toml          # Build + Entry-Point + Ruff + Pytest
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── install.ps1             # Desktop-Shortcut + Startmenu + Autostart
├── uninstall.ps1           # Shortcuts entfernen
├── run.ps1                 # Terminal-Start (alternativ)
├── make_icon.py            # generiert voice-flow.ico (Pillow)
├── voice-flow.ico          # generiert, in .gitignore
└── galvanek_context.txt    # Custom-Vokabular
```
