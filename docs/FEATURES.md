# Voice Flow — Complete Feature Reference

Everything Voice Flow does, why it exists, and how to control it.
For installation, see **[macOS](INSTALL-MACOS.md)** and **[Windows](INSTALL-WINDOWS.md)**.

---

## 1. Dictation — the core loop

Press one key, speak, press it again. The text is typed into whatever window
your cursor is in — Gmail, ClickUp, Word, a browser field, Claude Code, anything.

| Step | What happens |
|---|---|
| **Press** the record key | Recording starts. A pill appears at the bottom of the screen. System audio is muted (Windows) so playback does not bleed into the microphone. |
| **Speak** | Audio is written to disk **while you talk**, not just at the end. |
| **Press** again | Recording stops, audio goes to OpenAI, the text comes back and is pasted at the cursor. |

The transcribed text also stays on the clipboard, so **Ctrl+V / Cmd+V works even
if the paste landed in the wrong window**. This is deliberate: the clipboard is
*not* restored to its previous contents.

### Hold instead of toggle

The default is toggle (press to start, press to stop). Push-to-talk is available:

```
VOICE_FLOW_HOTKEY_MODE=hold
```

### Minimum length

Recordings shorter than **0.3 seconds** are discarded — that is a double tap, not
a dictation.

---

## 2. Keys

| macOS | Windows | Action |
|---|---|---|
| **F5** | **F8** | Start / stop recording |
| **F3** | **F7** | Screenshot of the monitor under the mouse pointer |
| **F6** | **F6** | Annotate: draw on screen, then capture |
| **ESC** | **ESC** | Cancel annotation |
| **Ctrl+Shift+Alt+Q** | **Ctrl+Shift+Alt+Q** | Quit Voice Flow |

The platforms differ on purpose: on a MacBook, F8 is Play and F7 is Previous
Track. Those belong to your music, so macOS uses F5 and F3 instead.

All keys are configurable:

```
VOICE_FLOW_HOTKEY=f5
VOICE_FLOW_SCREENSHOT_HOTKEY=f3
VOICE_FLOW_ANNOTATE_HOTKEY=f6
```

---

## 3. Screenshots inside a dictation

This is what makes Voice Flow more than a dictation tool. While recording, you
can capture screenshots, and they are **woven into the transcript at the point
where you were speaking about them**.

### How the weaving works

The transcription API returns text without word-level timestamps. So Voice Flow
places each screenshot **proportionally**: a shot taken at second 30 of a
90-second recording lands roughly one third into the text, snapped to the nearest
sentence boundary. The order and rough position are always right.

Example result in Claude Code mode:

```
Here is the customer list, it loads far too slowly.
(see shot_01.png in bucket: /Users/you/voice-flow/sessions/2026-08-19_03-10-53/shot_01.png)
And this filter over here returns the wrong rows.
(see shot_02.png in bucket: /Users/you/voice-flow/sessions/2026-08-19_03-10-53/shot_02.png)
```

### Where the files go

Every recording gets its own session folder:

```
~/voice-flow/sessions/2026-08-19_03-10-53/
    shot_01.png
    shot_02.png
    transcript.md          the transcript on its own
    bundle.md              transcript plus Markdown image references
```

---

## 4. Target mode — the switch left of the pill

Screenshots are useless if the receiver cannot open them. The switch decides
**how** they travel.

| Mode | What is pasted | Use for |
|---|---|---|
| **Claude Code** (default) | Text with the **absolute file path** of each screenshot | Claude Code, any local agent, terminal tools — they can open the file themselves |
| **AI-Web** | Text with `(siehe Bild 1)` markers **plus the images themselves**, pasted as real image data | ChatGPT, Claude in the browser, Lovable, Gemini — the web has no access to your file system |

Click the chip to switch. It shows the mark of its target: **Clawd**, the Claude
Code mascot, or the round **Chrome** mark.

### Why AI-Web pastes twice

Browsers drop `text/plain` from the clipboard as soon as files are present — you
would get the images and lose the words. So Voice Flow does it in two steps:
first the text, then the images. The success message tells you how many images
went along.

The mode is remembered between runs.

---

## 5. Annotation — draw before you capture

Press **F6** (or the pen button right of the pill). The screen dims, a toolbar
appears, and you can draw.

| Button | Action |
|---|---|
| **Pen** | Toggles drawing; clicking it again closes the toolbar |
| **Undo** | Removes the last stroke |
| **Redo** | Brings it back |
| **Clear** | Removes everything |
| **Camera** | Captures the screen **including** your drawings |
| **X** | Cancels without capturing |

### Shape snapping

Rough freehand becomes a clean shape when you release the mouse: a scribbled
circle turns into an ellipse, a rough box into a rectangle, a line with a hook
into an arrow. Ellipse and rectangle are compared against the same bounding box
and the better fit wins, so a box does not become a circle.

### Nothing disappears on its own

Strokes stay until **you** clear them. An earlier version faded them after a few
seconds, which threw away work mid-thought.

---

## 6. The Voice Flow window

Opens on start and from the tray icon. Closing it (X) quits Voice Flow.

- **Status** — Ready, Recording, Transcribing, Error
- **Key legend** — the correct keys for your platform
- **Microphone picker** — choose your input device without restarting
- **Permissions & transcripts** — see below
- Signature: *developed with ❤️ by Bastian Galvanek*

### Permissions & transcripts panel

Four rows, each with a green or red dot, refreshed every 2.5 seconds:

| Row | Green means |
|---|---|
| **Microphone** | Recording is allowed |
| **Accessibility** | Keys are detected and text can be pasted (macOS only) |
| **Screen Recording** | Screenshots show the real screen (macOS only) |
| **Transcripts** | Every recording has text |

Repair buttons appear **only when something is actually wrong**. This panel
exists so the app never has to interrupt you with a dialog — the state is simply
always visible.

On Windows the three permission rows are always green; Windows does not require
these grants.

---

## 7. Nothing is ever lost

The strongest guarantee in this tool. Four independent layers:

### Live spooling to disk

While you speak, audio is continuously written to a `_partial.wav` file that is a
**valid WAV at every moment**. If the process is killed, the machine crashes, or
power fails, the recording up to that second survives.

### A hanging audio system cannot freeze you

macOS CoreAudio can deadlock when the microphone changes mid-recording — `stop()`
never returns. Voice Flow stops waiting after a timeout, delivers the audio it
has, and keeps the rescue file. (Real incident, 16 August 2026: 2 minutes 54
seconds existed only in the RAM of a frozen process.)

### Hallucination detection

If the microphone delivers garbage — a Bluetooth headset in 8 kHz hands-free
mode, for example — the transcription may come back as a short phrase in the
wrong language. Voice Flow measures **words per second**: normal speech is 2–3,
and anything far below that at meaningful length is marked *suspect*. The
recording is **kept for a retry** instead of being deleted. (Real incident, 7
July 2026: 266 seconds of audio became 12 English words and the audio was
deleted.)

### Archive instead of delete

After a successful transcription the WAV is converted to a small Opus archive
(~1 MB per 10 minutes) rather than deleted, and kept for **one year**. A dictation
is often only recognised as flawed days later.

```
VOICE_FLOW_RETENTION_DAYS=365
VOICE_FLOW_MAX_ARCHIVE_MB=5000
```

### Catching up

Recordings that never got text show in the window as **"N without text"**, with a
button to transcribe them now, showing live progress ("7 of 18 …"). Failed
starts under 1.5 seconds of audio are not counted — they never contained speech —
but they are still not deleted.

When catching up, orphaned screenshot folders are matched back to their recording
by timestamp, so the images end up in the transcript even for a recovery run.

---

## 8. Long recordings

Recordings longer than **5 minutes 30 seconds** are split into 5-minute pieces
and transcribed separately. The cut is **not** made at a fixed second but at the
quietest point in a search window around it — otherwise a word gets cut in half
and both halves come back as noise.

This removed the entire "recording too long" failure class. (Real incident, 11
July 2026: a 14.5-minute dictation was lost because a 25 MB limit was checked on
raw WAV bytes before compression — the compressed file would have been 2.4 MB.)

---

## 9. Transcript history

Every successful dictation is stored twice:

```
~/.voice-flow/transcripts/transcripts.jsonl   one line per entry, structured
~/.voice-flow/transcripts/transcripts.txt     readable, grouped by day
```

So you can always find what you said, even if the paste went into the wrong
window. History failures never block dictation.

---

## 10. Language and models

| Setting | Default | Note |
|---|---|---|
| `VOICE_FLOW_LANGUAGE` | `de` | `auto` is available but was the cause of wrong-language hallucinations on poor audio |
| `VOICE_FLOW_WHISPER_MODEL` | `gpt-4o-mini-transcribe` | About 4× faster than `whisper-1` at comparable quality for speech |
| `VOICE_FLOW_CLEANUP_MODEL` | `claude-haiku-4-5-20251001` | Only used if cleanup is enabled |

English words inside German speech are transcribed correctly; fixing the language
only stops the detector from flipping to a foreign language on muddy audio.

### Optional cleanup pass

Off by default, because it needs a second API key. When enabled, Claude Haiku
tidies the raw transcription — filler words, punctuation, and domain vocabulary
from `galvanek_context.txt` if that file exists.

```
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 11. Notifications

Small toasts in the corner, never stealing focus:

- **Screenshot taken** — with a thumbnail and a button to open the folder
- **Paste done** — word count, duration, number of images included
- **Recordings without text** — with a button to catch up
- **Errors** — in plain language, not a stack trace

---

## 12. Configuration reference

All settings live in one file:

- **macOS**: `~/.voice-flow/.env`
- **Windows**: `%USERPROFILE%\.voice-flow\.env`

```ini
# Required
OPENAI_API_KEY=sk-...

# Optional
ANTHROPIC_API_KEY=sk-ant-...              # enables the cleanup pass
VOICE_FLOW_HOTKEY=f5                      # record key
VOICE_FLOW_HOTKEY_MODE=toggle             # toggle | hold
VOICE_FLOW_SCREENSHOT_HOTKEY=f3
VOICE_FLOW_ANNOTATE_HOTKEY=f6
VOICE_FLOW_LANGUAGE=de                    # or auto
VOICE_FLOW_WHISPER_MODEL=gpt-4o-mini-transcribe
VOICE_FLOW_CLEANUP_MODEL=claude-haiku-4-5-20251001
VOICE_FLOW_AUDIO_DEVICE=Poly              # device index, or part of its name
VOICE_FLOW_RETENTION_DAYS=365
VOICE_FLOW_MAX_ARCHIVE_MB=5000
```

Naming the microphone by **part of its name** is more robust than an index —
device indices shift when you plug something in.

---

## 13. Where everything lives

```
~/.voice-flow/
    .env                       your keys and settings
    logs/voice-flow.log        what the app did, newest at the bottom
    recordings/                audio archive (one year)
    transcripts/               history, JSONL and plain text
    state/                     small internal markers

~/voice-flow/sessions/<timestamp>/
    shot_01.png, shot_02.png   screenshots of that dictation
    transcript.md, bundle.md   transcript, and transcript with image links
```

Uninstalling never touches these folders.

---

## 14. Details you may run into

**Only one instance runs.** Starting Voice Flow a second time makes the running
instance show its ready pill instead of starting a competing process.

**System audio is muted while recording** (Windows). If the app crashes or is
killed, audio is unmuted anyway — you will never be left with silent headphones.

**The pill does not intercept clicks.** It is click-through by design, so it can
never block the window you are dictating into. That is why the mode chip and pen
are separate small windows next to it.

**Voice Flow never targets itself.** If Voice Flow was the front application when
you started recording, it does not pull itself forward afterwards — that used to
pop the minimized window back open.

---

developed with ❤️ by Bastian Galvanek
