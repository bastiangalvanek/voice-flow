# Voice Flow on macOS — Setup in 5 minutes

Dictate with one key. The text lands wherever your cursor is.
For what the app can do, see the **[Feature Reference](FEATURES.md)**.

---

## 1. Install the app

1. Download **`VoiceFlow-vX.Y.Z-macOS.dmg`** from
   [Releases](https://github.com/bastiangalvanek/voice-flow/releases/latest)
2. Double-click the DMG
3. Drag **Voice Flow** onto **Applications**
4. Eject the DMG

### First launch: "Apple could not verify…"

This appears because the app is self-built and not registered with Apple.
It is not an error.

**Right-click Voice Flow → Open → Open again in the dialog.**
Only needed the very first time.

---

## 2. Add your OpenAI key

Without a key there is no transcription. The key stays on your machine and is
**not** part of the app — which is why no download contains one.

Open Terminal and paste this line (replace the key):

```bash
mkdir -p ~/.voice-flow && echo "OPENAI_API_KEY=sk-YOUR-KEY" > ~/.voice-flow/.env
```

Get a key at [platform.openai.com/api-keys](https://platform.openai.com/api-keys).

---

## 3. The three permissions

macOS asks for each one separately. All three are shown permanently in the Voice
Flow window under **Permissions & transcripts** with a green or red dot, so you
can always see what is missing.

| Permission | Needed for | Where |
|---|---|---|
| **Microphone** | Recording | Dialog on first launch |
| **Accessibility** | Detecting F5/F3/F6 and pasting text | System Settings → Privacy & Security → Accessibility |
| **Screen Recording** | Screenshots (F3/F6) | System Settings → Privacy & Security → Screen Recording |

**After granting a permission, quit Voice Flow and start it again.** macOS only
applies these on a fresh launch.

### If Screen Recording is ticked but still does not work

This happens when the entry belongs to an older build of the app: the checkbox is
there, but it no longer applies. macOS stores the app's code signature at the
moment you grant it, and a stale entry is never cleaned up or flagged.

In the Voice Flow window press **"Bildschirm-Freigabe reparieren"**. It removes
the dead entry, asks macOS again, and opens the list. Then restart the app.

You can tell your screenshots are affected easily: they show only the desktop
background and Voice Flow's own windows, with every other app missing.

---

## 4. Keys

| Key | Action |
|---|---|
| **F5** | Start / stop recording — the text is pasted when you stop |
| **F3** | Screenshot of the monitor under the mouse pointer |
| **F6** | Annotate: draw, then capture |
| **Cmd+Shift+V** | Paste the last dictation again — text, then all images |
| **ESC** | Cancel annotation |
| **Ctrl+Shift+Alt+Q** | Quit Voice Flow |

macOS uses F5 and F3 instead of Windows' F8 and F7, because on a MacBook those
keys are Play and Previous Track — they belong to your music.

### The switch left of the pill

It decides **how** screenshots travel when the text is pasted:

- **Claude Code** — the text carries the absolute file paths of the images
- **AI-Web** — the images are additionally pasted as real images (ChatGPT, Claude
  in the browser, Lovable). The web has no access to your file system.

Click to switch. Default is Claude Code.

### Wrong tab? Just Cmd+V

In AI-Web mode, as long as your dictation is still the newest thing on the
clipboard, a plain **Cmd+V** re-runs the whole cascade — first the text, then
every screenshot. The moment you copy anything else, Cmd+V is instantly the
normal paste again. **Cmd+Shift+V** does the same explicitly, in every mode,
even after you copied something else in between.

### The pen right of the pill

Opens the same toolbar as F6: pen, undo, redo, clear, capture. Rough shapes are
snapped clean (circle, rectangle, arrow). Nothing disappears on its own — strokes
are only removed by **Clear**.

---

## 5. If something is missing

The Voice Flow window tells you:

- **Transcripts: "N without text"** — recordings whose transcription did not
  complete (network dropped, app crashed). The button **"Fehlende Transkripte
  nachholen"** processes them now. **Recordings are never deleted**; they are
  kept for a year under `~/.voice-flow/recordings/`.
- Log for troubleshooting: `~/.voice-flow/logs/voice-flow.log`

---

## 6. Uninstall

Move **Voice Flow** from Applications to the Trash. Your keys, recordings and
transcripts under `~/.voice-flow/` and `~/voice-flow/` stay — delete that folder
by hand if you want them gone too.

---

developed with ❤️ by Bastian Galvanek
