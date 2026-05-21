# Voice Flow

Push-to-talk dictation tool for Windows. **Hold F8**, speak, release — the transcribed text lands in the active window (Gmail, Slack, Word, browser, anywhere).

**Stack:** OpenAI Whisper (transcription) + optional Claude (cleanup with custom vocabulary).

> Currently Windows-only. macOS / Linux ports are welcome via PR — see [Porting](#porting) below.

---

## Quick start (Windows)

You need:
- Python 3.10+ installed and on `PATH`
- An OpenAI API key from <https://platform.openai.com/api-keys>

```powershell
git clone https://github.com/galvabst/voice-flow.git
cd voice-flow
.\install.ps1
```

`install.ps1` will:

1. Create a virtual env (`.venv`)
2. Install the package (`pip install -e .`)
3. Copy `.env.example` to `.env` and open Notepad so you can paste your API key
4. Generate `voice-flow.ico`
5. Create a Desktop shortcut + Start Menu entry
6. Ask whether you want autostart on Windows login

Then: double-click **Voice Flow** on the desktop. The tray icon appears (grey = idle). Place your cursor in any text field, **hold F8**, speak, release.

Uninstall: `.\uninstall.ps1` (removes the shortcuts; `.venv` and code stay).

---

## Configuration via `.env`

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | **required** | OpenAI Whisper transcription |
| `ANTHROPIC_API_KEY` | optional | If set, enables Claude cleanup |
| `VOICE_FLOW_ENABLE_CLEANUP` | `0` | `1` / `true` / `yes` / `on` to enable cleanup |
| `VOICE_FLOW_HOTKEY` | `f8` | Push-to-talk key |
| `VOICE_FLOW_LANGUAGE` | `auto` | Whisper language (ISO code or `auto`) |
| `VOICE_FLOW_WHISPER_MODEL` | `gpt-4o-mini-transcribe` | Whisper model |
| `VOICE_FLOW_CLEANUP_MODEL` | `claude-haiku-4-5-20251001` | Cleanup model |
| `VOICE_FLOW_AUDIO_DEVICE` | system default | Mic index from `--list-devices` |

CLI flags override `.env`.

### `.env` lookup order

Voice Flow looks for `.env` in these locations and uses the **first one** it finds:

1. Next to the executable (or repo root when running from source)
2. `%APPDATA%\voice-flow\.env` — this is where the first-run wizard writes its file

The wizard (see next section) automatically puts your key in location 2, so you usually don't need to touch any file manually.

---

## CLI

```powershell
voice-flow                     # default: tray + sound
voice-flow --verbose           # debug logging
voice-flow --no-tray           # without tray icon
voice-flow --no-cleanup        # raw Whisper output, no Claude cleanup
voice-flow --no-sound          # no beeps
voice-flow --hotkey f9         # different push-to-talk key
voice-flow --device 1          # mic index (see --list-devices first)
voice-flow --list-devices      # list microphone indexes
```

---

## Custom vocabulary: `context.txt`

Create a `context.txt` in the repo root (gitignored — your file, your data). It will be:

- passed as a **Whisper prompt** (first ~220 chars) — helps proper-noun recognition
- used as a **Claude system prompt** for cleanup — for substitutions like "kubernetes" → "Kubernetes"

A template is in `context.example.txt`. Copy it to `context.txt` and edit.

---

## Where your data lives

| Path | Contents |
|---|---|
| `~/.voice-flow/recordings/` | WAV backups (deleted after success; failed ones kept) |
| `~/.voice-flow/transcripts/` | `transcripts.jsonl` + `transcripts.txt` — every dictation |
| `~/.voice-flow/logs/` | Rotating log file (max 6 MB total) |

Everything stays on **your** machine. The only network calls are to OpenAI (and Anthropic if cleanup is enabled).

---

## Architecture

```
F8 down ─┐
         ├─ AudioRecorder (sounddevice, 16 kHz mono int16)
F8 up   ─┘
                 │
                 ▼
         WAV bytes (in memory)
                 │
                 ▼
         Transcriber  ── OpenAI Whisper + selective retry
                 │
                 ▼
         Cleaner      ── Claude Haiku + context (optional)
                 │
                 ▼
         paste_to_active_window  ── clipboard + Ctrl+V
```

### Modules

| File | Responsibility |
|---|---|
| `src/voice_flow/config.py` | `.env` + CLI overrides → immutable `Config` dataclass |
| `src/voice_flow/audio.py` | `AudioRecorder` — sounddevice stream, thread-safe |
| `src/voice_flow/transcription.py` | OpenAI Whisper client with selective retry |
| `src/voice_flow/cleanup.py` | Anthropic Claude client, optional |
| `src/voice_flow/paste.py` | Clipboard-based paste with restore |
| `src/voice_flow/audio_mute.py` | Mute system audio during recording (pycaw) |
| `src/voice_flow/sound.py` | `winsound.Beep` feedback |
| `src/voice_flow/tray.py` | `pystray` system tray with colored status icon |
| `src/voice_flow/overlay_qt.py` | PyQt6 floating pill overlay (recording / processing / success) |
| `src/voice_flow/app.py` | `VoiceFlowApp` — controller / state machine |
| `src/voice_flow/cli.py` | argparse entry point, banner |
| `src/voice_flow/logging_setup.py` | Console + rotating file logging |
| `src/voice_flow/singleton.py` | Port-based singleton lock + IPC |
| `src/voice_flow/recording_storage.py` | WAV backup on disk before API call |
| `src/voice_flow/transcript_history.py` | Persistent JSONL + TXT history |

---

## Tests

```powershell
pip install -e ".[dev]"
pytest
```

Smoke tests for config loading, cleanup fallback, audio recorder lifecycle.
Whisper / Claude / paste are I/O — exercise them manually.

---

## Build a standalone EXE

```powershell
pip install -e ".[build]"
python make_icon.py              # generates voice-flow.ico (one-time per logo change)
pyinstaller voice-flow.spec
# → dist/voice-flow.exe (single file, no Python required to run)
```

The resulting `.exe` is ~80–120 MB (bundles Python + PyQt6 + numpy). On first launch it shows a **first-run wizard** that asks for the OpenAI API key (and optionally an Anthropic key) and writes it to `%APPDATA%\voice-flow\.env`. The end user never needs to touch a file.

**Unsigned EXE warning:** Windows SmartScreen will show "Unknown publisher" since the EXE isn't code-signed. Users click "More info" → "Run anyway". For wider distribution, get a code-signing cert (~€80/year from Sectigo) and add `codesign_identity=` to the spec.

---

## Porting (macOS / Linux)

Today this is Windows-only. To port:

| Module | Windows dependency | Replace with |
|---|---|---|
| `audio_mute.py` | `pycaw` (Core Audio) | macOS: CoreAudio / AVAudioSession. Linux: PulseAudio / PipeWire. Or just skip the feature. |
| `keyboard` (cli.py, paste.py) | global hotkey | `pynput` (cross-platform, but on macOS needs Accessibility permission) |
| `paste.py` | `Ctrl+V` | macOS: `Cmd+V` |
| `sound.py` | `winsound.Beep` | macOS: `afplay` / `NSSound`. Linux: `aplay`. |
| `gui_errors.py` | `MessageBoxW` (Win32) | macOS: `osascript`. Linux: `zenity`. |
| `install.ps1` | PowerShell | Shell script + Homebrew / apt notes |

PRs welcome.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| **F8 doesn't react** | Start PowerShell as Admin — the `keyboard` library often needs global-hotkey privileges |
| **Wrong microphone** | `voice-flow --list-devices` → pick the index → `voice-flow --device N` or set `VOICE_FLOW_AUDIO_DEVICE` |
| **Tray doesn't appear** | `voice-flow --no-tray --verbose` → check `~/.voice-flow/logs/voice-flow.log` |
| **Whisper mishears names** | Add the names to `context.txt`, put the most-important block first (becomes the Whisper prompt) |
| **Latency > 3 s** | OpenAI Whisper API dominates. Local Whisper (faster-whisper + CUDA) is on the roadmap. |
| **Silent recording** | Check default mic in Windows sound settings; use `--list-devices` and `--device N` |

---

## License

MIT — see [LICENSE](LICENSE).
