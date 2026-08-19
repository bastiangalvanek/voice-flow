# Voice Flow on Windows — Setup in 5 minutes

Dictate with one key. The text lands wherever your cursor is.
For what the app can do, see the **[Feature Reference](FEATURES.md)**.

---

## 1. Install the app

1. Download **`VoiceFlow-X.Y.Z-Setup.exe`** from
   [Releases](https://github.com/bastiangalvanek/voice-flow/releases/latest)
2. Double-click it. A normal installer window opens (in German).
3. Click through. Two options are offered:
   - **Desktop shortcut** (recommended)
   - **Start with Windows** (handy if you dictate daily)
4. Done. Voice Flow is in the Start menu.

**No administrator rights required** — it installs into your user folder
(`%LOCALAPPDATA%\Programs\Voice Flow`).

Prefer no installer? Take `VoiceFlow-X.Y.Z-Windows.zip`, unpack it anywhere and
run `VoiceFlow.exe`.

### "Windows protected your PC"

This appears because the app is self-built and not registered with Microsoft.
Not an error.

**More info → Run anyway.**

---

## 2. Add your OpenAI key

Without a key there is no transcription. The key stays on your machine and is
**not** part of the app — which is why no download contains one.

Press **Windows + R**, paste this, press Enter:

```
notepad %USERPROFILE%\.voice-flow\.env
```

If Notepad says the file does not exist, choose **Yes** to create it. If the
folder is missing too, run this first (Windows + R):

```
cmd /c mkdir %USERPROFILE%\.voice-flow
```

The file needs exactly one line:

```
OPENAI_API_KEY=sk-YOUR-KEY
```

Save, close, start Voice Flow. Get a key at
[platform.openai.com/api-keys](https://platform.openai.com/api-keys).

---

## 3. Keys

| Key | Action |
|---|---|
| **F8** | Start / stop recording — the text is pasted when you stop |
| **F7** | Screenshot of the monitor under the mouse pointer |
| **F6** | Annotate: draw, then capture |
| **Ctrl+Shift+V** | Paste the last dictation again — text, then all images |
| **ESC** | Cancel annotation |
| **Ctrl+Shift+Alt+Q** | Quit Voice Flow |

> macOS uses F5 and F3 instead — on a MacBook, F8 and F7 are media keys.

### The switch left of the pill

It decides **how** screenshots travel when the text is pasted:

- **Claude Code** — the text carries the absolute file paths of the images
- **AI-Web** — the images are additionally pasted as real images (ChatGPT, Claude
  in the browser, Lovable). The web has no access to your file system.

Click to switch. Default is Claude Code.

### Wrong tab? Paste it again

Click the right field and press **Ctrl+Shift+V**. The whole last dictation goes
in again: first the text, then every screenshot. Useful when a chat swallowed the
attachments or you hit the wrong tab.

### The pen right of the pill

Opens the same toolbar as F6: pen, undo, redo, clear, capture. Rough shapes are
snapped clean (circle, rectangle, arrow). Nothing disappears on its own — strokes
are only removed by **Clear**.

---

## 4. If something is missing

The Voice Flow window tells you, under **Permissions & transcripts**:

- **Transcripts: "N without text"** — recordings whose transcription did not
  complete (network dropped, app crashed). The button **"Fehlende Transkripte
  nachholen"** processes them now. **Recordings are never deleted**; they are
  kept for a year under `%USERPROFILE%\.voice-flow\recordings\`.
- Log for troubleshooting: `%USERPROFILE%\.voice-flow\logs\voice-flow.log`

The three permission rows (microphone, accessibility, screen recording) are
always green on Windows — Windows does not require these grants.

### Microphone not found

Windows Settings → Privacy & security → Microphone → turn on
**"Let apps access your microphone"** and, below it,
**"Let desktop apps access your microphone"**.

### System sound is muted while recording

That is intentional — playback would otherwise bleed into the microphone. If the
app crashes or is killed, sound is unmuted anyway; you will never be left with
silent headphones.

---

## 5. Uninstall

Windows Settings → Apps → **Voice Flow** → Uninstall.

Recordings, transcripts and your key under `%USERPROFILE%\.voice-flow\` remain —
delete that folder by hand if you want them gone too.

---

## How this installer is tested

Every release is installed, launched and uninstalled on a real Windows machine
before the files go online. If any of those steps fails, the release does not
publish. What is **not** covered there is how the window *looks* — the build
machine has no screen. That part is checked by hand on macOS.

---

developed with ❤️ by Bastian Galvanek
