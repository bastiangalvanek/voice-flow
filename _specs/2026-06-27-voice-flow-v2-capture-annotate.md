# Voice Flow v2 — Capture + Annotate + Smart-Dump Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Voice Flow vom reinen Push-to-Talk-Diktat zu einem multimodalen Capture-Tool ausbauen: F8-Toggle-Aufnahme, Screenshots (instant + mit Zeichnung) sauber in Session-Buckets, und ein kontext-bewusster Dump (Text + Bilder) ins gerade fokussierte Fenster — plus Fix des fehlenden Galvanek-Flocke-Logos.

**Architecture:** Additive Erweiterung des bestehenden Python-Pakets `src/voice_flow/`. Neue Module pro Verantwortung (`screenshot.py`, `session.py`, `annotate.py`, `smart_paste.py`), bestehende Module (`app.py`, `cli.py`, `config.py`, `tray.py`, `overlay_qt.py`) minimal-invasiv erweitert. Die Aufnahme-Session ist die zentrale Klammer: F8-Start öffnet sie, F7/F6 fügen Screenshots hinzu, F8-Stop transkribiert + baut ein `bundle.md`. Das Zeichen-Overlay läuft im **bestehenden** Qt-Thread (eine QApplication pro Prozess) und wird via thread-safe Signals erzeugt/zerstört.

**Tech Stack:** Python 3.14, PyQt6 (Overlay + Zeichnen, bereits Dependency), `mss` (Screenshot, NEU), Pillow (Compositing, bereits da), `keyboard` (Hotkeys, bereits da), `pyperclip` (Text-Clipboard, bereits da), `pywin32`/`win32clipboard` (Rich-/Bild-Clipboard, NEU, nur Phase 3), `ctypes` (Cursor-Position, Foreground-Window — keine neue Dependency).

## Global Constraints

- **Plattform:** Windows 11 only. Multi-Monitor + Per-Monitor-DPI müssen korrekt behandelt werden (Cursor-Monitor-Erkennung, Koordinaten→Pixel-Mapping).
- **Keine KI-Striche:** Niemals em-dash/en-dash in User-sichtbarem Text (Overlay-Labels, bundle.md, Logs). Bindestrich oder Punkt.
- **Modul-Disziplin:** Keine Datei > ~300 Zeilen, eine Verantwortung pro Modul. `overlay_qt.py` ist schon 651 Zeilen — das Zeichen-Overlay kommt in ein **eigenes** Modul `annotate.py`, nicht hinein.
- **Nur additiv am bestehenden Tool.** Bestehende Hold-Mode-Pfade bleiben lauffähig (Config-Schalter), nichts wird ersatzlos entfernt was der User noch nutzen könnte.
- **Bastian-Decisions als Kommentar markieren** (wie im Bestand: `# 27.06 Bastian: …`).
- **I/O ehrlich testen:** Pure Logik (Pfad-Bau, Monitor-Auswahl, Target-Klassifikation, Bundle-Assembly) bekommt echte Unit-Tests. Qt/Screenshot/Clipboard/Hotkey sind I/O → explizite manuelle Verify-Schritte mit erwarteter Beobachtung. Keine Fake-Tests die nur Kompilierung prüfen.

---

## File Structure

| Datei | Verantwortung | Status |
|---|---|---|
| `src/voice_flow/config.py` | + `hotkey_mode`, `screenshot_hotkey`, `annotate_hotkey`, `dump_hotkey`, `sessions_dir` | Modify |
| `src/voice_flow/tray.py` | Flocke als echtes Icon + Status-Punkt-Badge statt Flat-Tint | Modify |
| `src/voice_flow/logo_loader.py` | Robuste Logo-Auflösung (logo.png → Flocke-PNG → None), shared von tray + overlay | Create |
| `src/voice_flow/screenshot.py` | `grab_monitor_under_cursor()`, reine `pick_monitor()` | Create |
| `src/voice_flow/session.py` | `Session`: Bucket-Dir, add_screenshot, set_transcript, build_bundle | Create |
| `src/voice_flow/annotate.py` | PyQt6 transparentes Vollbild-Zeichen-Overlay + Mini-Toolbar + Fade + Composite | Create |
| `src/voice_flow/smart_paste.py` | `classify_target()`, Dump-Strategien (vscode/plain/rich/browser) | Create |
| `src/voice_flow/app.py` | Toggle-Handler, Screenshot-Handler, Session-Lifecycle, Dump-Handler | Modify |
| `src/voice_flow/cli.py` | Hotkey-Wiring (toggle + F7/F6/F9), Banner | Modify |
| `logo.png` | Generierte quadratische Flocke (transparent, getrimmt) | Create |
| `tests/test_session.py`, `test_screenshot.py`, `test_smart_paste.py`, `test_toggle.py` | Unit-Tests pure Logik | Create |

---

## Phase 0 — Quick Wins (Flocke + Toggle, zuerst shippen)

### Task 1: Flocke-Logo-Fix (Tray + Pille)

**Root Cause (verifiziert):** `tray.py:12` und `overlay_qt.py:35` laden `voice-flow/logo.png`. Die Datei existiert nicht (im Ordner liegt `LinkedIn Galvanek Profil Flocke (2).png`). Tray fällt auf gemalten Kreis zurück, Pille zeigt kein Logo. Zweiter Defekt: `tray._tint_logo` färbt das ganze Logo flach in eine Status-Farbe.

**Files:**
- Create: `src/voice_flow/logo_loader.py`
- Create: `logo.png` (aus Flocke-Quelle generiert)
- Modify: `src/voice_flow/tray.py` (Logo-Laden + Status-Punkt statt Flat-Tint)
- Modify: `src/voice_flow/overlay_qt.py:35` (LOGO_PATH über logo_loader)
- Test: `tests/test_logo_loader.py`

**Interfaces:**
- Produces: `logo_loader.resolve_logo_path() -> Path | None` (erstes existierendes aus Kandidaten-Liste), `logo_loader.LOGO_CANDIDATES: list[Path]`.

- [ ] **Step 1: logo.png aus Flocke-Quelle generieren**

```bash
cd "c:/Users/Bastian/Downloads/claude code/apps/tools/voice-flow"
python -c "
from PIL import Image
src = Image.open('LinkedIn Galvanek Profil Flocke (2).png').convert('RGBA')
# Auf nicht-transparente Bounding-Box trimmen, dann quadratisch padden
bbox = src.getchannel('A').getbbox()
src = src.crop(bbox) if bbox else src
side = max(src.size)
canvas = Image.new('RGBA', (side, side), (0,0,0,0))
canvas.paste(src, ((side-src.size[0])//2, (side-src.size[1])//2), src)
canvas.save('logo.png')
print('logo.png', canvas.size)
"
```
Expected: `logo.png (NNN, NNN)` — quadratische, getrimmte Flocke liegt als `logo.png` im Ordner.

- [ ] **Step 2: Failing test für logo_loader**

```python
# tests/test_logo_loader.py
from voice_flow import logo_loader

def test_resolve_returns_existing_logo():
    p = logo_loader.resolve_logo_path()
    assert p is not None
    assert p.exists()
    assert p.name == "logo.png"
```

Run: `pytest tests/test_logo_loader.py -v`
Expected: FAIL (`module voice_flow has no attribute logo_loader`).

- [ ] **Step 3: logo_loader.py implementieren**

```python
# src/voice_flow/logo_loader.py
from __future__ import annotations
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]  # voice-flow/

# 27.06 Bastian: Flocke-Bug. logo.png fehlte, daher Fallback-Kreis. Robuste
# Kandidaten-Kette: erst logo.png, dann die Original-Flocke-Datei.
LOGO_CANDIDATES = [
    _ROOT / "logo.png",
    _ROOT / "LinkedIn Galvanek Profil Flocke (2).png",
]


def resolve_logo_path() -> Path | None:
    for c in LOGO_CANDIDATES:
        if c.exists():
            return c
    return None
```

- [ ] **Step 4: Test grün**

Run: `pytest tests/test_logo_loader.py -v`
Expected: PASS.

- [ ] **Step 5: tray.py auf echte Flocke + Status-Punkt umstellen**

Ersetze in `tray.py` die LOGO_PATH-Konstante und `_icon_for`/`_tint_logo` durch: Flocke unverändert laden, kleinen farbigen Status-Punkt unten-rechts aufmalen.

```python
# tray.py — Kopf
from voice_flow.logo_loader import resolve_logo_path
LOGO_PATH = resolve_logo_path()  # statt fixem Pfad

# in __init__:
self._has_logo = LOGO_PATH is not None

# _icon_for unverändert lassen, aber _tint_logo ersetzen durch _logo_with_badge:
def _logo_with_badge(self, color: tuple[int, int, int]) -> "Image.Image":
    """Echte Flocke (Farben erhalten) + Status-Punkt unten-rechts."""
    try:
        base = Image.open(LOGO_PATH).convert("RGBA")
    except Exception as ex:
        log.warning("logo.png nicht ladbar: %s — Fallback.", ex)
        return self._draw_fallback(color)
    base.thumbnail((64, 64), Image.LANCZOS)
    canvas = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    canvas.paste(base, ((64 - base.size[0]) // 2, (64 - base.size[1]) // 2), base)
    draw = ImageDraw.Draw(canvas)
    r = 11
    draw.ellipse((64 - 2 * r - 2, 64 - 2 * r - 2, 62, 62), fill=color + (255,))
    draw.ellipse((64 - 2 * r - 2, 64 - 2 * r - 2, 62, 62), outline=(255, 255, 255, 230), width=2)
    return canvas
```

Und in `_icon_for` den Aufruf `self._tint_logo(color)` → `self._logo_with_badge(color)`. `idle` nutzt grauen Punkt (dezent), `recording` roten, `processing` orangenen.

- [ ] **Step 6: overlay_qt.py Logo-Pfad robust**

In `overlay_qt.py:35` ersetzen:
```python
from voice_flow.logo_loader import resolve_logo_path
LOGO_PATH = resolve_logo_path()
```
Und in `PillWidget.__init__` (Zeile 136) `if LOGO_PATH and LOGO_PATH.exists():` statt `if LOGO_PATH.exists():`.

- [ ] **Step 7: Manuelle Verifikation (Tray + Pille zeigen Flocke)**

Run: `cd apps/tools/voice-flow && python -m voice_flow --verbose`
Erwartet/beobachten: Tray-Icon zeigt die **echte farbige Flocke** mit kleinem grauen Punkt. F8 drücken: Pille erscheint **mit Flocke links**, Tray-Punkt wird rot. Screenshot machen, im Chat als Beweis ablegen (`memory/_evidence/2026-06-27-voice-flow-v2/flocke-tray.png`).

- [ ] **Step 8: Commit**

```bash
git add -A 2>/dev/null || true
# (Kein Repo — stattdessen: Datei-Stand sichern, keine VCS-Aktion noetig.)
```
Hinweis: voice-flow ist **kein** Git-Repo. „Commit"-Schritte hier = logischer Checkpoint, kein `git`. Wenn Bastian es versionieren will, separat `git init` anbieten.

---

### Task 2: F8 = Toggle (drücken start, nochmal stop)

**Files:**
- Modify: `src/voice_flow/config.py` (+ `hotkey_mode: str = "toggle"`)
- Modify: `src/voice_flow/app.py` (+ `on_hotkey_toggle()`)
- Modify: `src/voice_flow/cli.py` (`_setup_toggle_hotkey`, Wiring, Banner-Text)
- Modify: `src/voice_flow/overlay_qt.py:226` (Sekundär-Text)
- Test: `tests/test_toggle.py`

**Interfaces:**
- Consumes: bestehende `app.on_hotkey_press()` / `app.on_hotkey_release()`.
- Produces: `app.on_hotkey_toggle() -> None` (idle→start-Aufnahme, recording→stop+Pipeline). `config.hotkey_mode in {"toggle","hold"}`.

- [ ] **Step 1: Failing test Toggle-State**

```python
# tests/test_toggle.py
from unittest.mock import MagicMock
from voice_flow.app import VoiceFlowApp
from voice_flow.config import Config

def _app():
    cfg = Config(openai_api_key="x", hotkey_mode="toggle", enable_overlay=False,
                 enable_audio_mute=False, enable_sound=False)
    app = VoiceFlowApp.__new__(VoiceFlowApp)
    app.config = cfg
    app.recorder = MagicMock()
    app.audio_mute = None
    app.overlay = None
    app.tray = None
    import threading
    app._state_lock = threading.Lock()
    app.state = VoiceFlowApp.STATE_IDLE
    app._hotkey_down = False
    app._auth_error_shown = False
    app._last_toggle = 0.0
    return app

def test_toggle_idle_starts_recording():
    app = _app()
    app.on_hotkey_toggle()
    assert app.state == VoiceFlowApp.STATE_RECORDING
    app.recorder.start.assert_called_once()
```

Run: `pytest tests/test_toggle.py::test_toggle_idle_starts_recording -v`
Expected: FAIL (`on_hotkey_toggle` existiert nicht).

- [ ] **Step 2: config.py erweitern**

```python
# config.py im @dataclass, nach hotkey:
# 27.06 Bastian: F8 jetzt Toggle (nicht halten). hold bleibt als Option.
hotkey_mode: str = "toggle"   # "toggle" | "hold"
```
Und in `load_config`: `hotkey_mode=os.getenv("VOICE_FLOW_HOTKEY_MODE", "toggle"),`.

- [ ] **Step 3: app.on_hotkey_toggle implementieren**

```python
# app.py — neue Methode. Debounce gegen Typematic-Doppelfeuer.
import time as _time

def on_hotkey_toggle(self) -> None:
    now = _time.monotonic()
    with self._state_lock:
        if now - getattr(self, "_last_toggle", 0.0) < 0.3:
            return
        self._last_toggle = now
        current = self.state
    if current == self.STATE_IDLE:
        self._start_recording()
    elif current == self.STATE_RECORDING:
        self._stop_recording()
    # PROCESSING: ignorieren (laeuft noch)
```

Refaktoriere den Body von `on_hotkey_press` (ab `self.state = RECORDING` Block) nach `_start_recording()` und `on_hotkey_release` nach `_stop_recording()`, sodass Toggle und Hold denselben Kern nutzen (DRY). `on_hotkey_press/release` rufen danach nur noch die Kern-Methoden mit dem Hold-Down-Flag-Handling.

- [ ] **Step 4: Test grün**

Run: `pytest tests/test_toggle.py -v`
Expected: PASS.

- [ ] **Step 5: cli.py — Toggle-Wiring**

```python
# cli.py
def _setup_toggle_hotkey(hotkey: str, on_toggle) -> None:
    # keyboard.add_hotkey feuert einmal pro Tastendruck (kein press/release).
    keyboard.add_hotkey(hotkey, on_toggle, suppress=False)

# in main(): statt _setup_hold_hotkey:
if cfg.hotkey_mode == "toggle":
    _setup_toggle_hotkey(cfg.hotkey, app.on_hotkey_toggle)
else:
    _setup_hold_hotkey(cfg.hotkey, app.on_hotkey_press, app.on_hotkey_release)
```
Banner-Text (`_print_banner`, `show_ready`) von „F8 halten" → „F8 = Start/Stop".

- [ ] **Step 6: Overlay-Text anpassen**

`overlay_qt.py:226` Sekundär-Text von `"loslassen zum senden"` → `"F8 zum Senden"`.

- [ ] **Step 7: Manuelle Verifikation**

Run: `python -m voice_flow --verbose`
F8 drücken (nicht halten) → Pille rot „Aufnahme · F8 zum Senden", reden, F8 nochmal → Processing → Text eingefügt. Mehrfach togglen, kein Doppel-Start. Screenshot als Beweis.

- [ ] **Step 8: Commit-Checkpoint** (kein git, siehe Task 1 Step 8).

---

## Phase 1 — Capture in Buckets

### Task 3: screenshot.py (Monitor unter der Maus grabben)

**Files:**
- Modify: `requirements.txt` / `pyproject.toml` (+ `mss>=9.0.0`)
- Create: `src/voice_flow/screenshot.py`
- Test: `tests/test_screenshot.py`

**Interfaces:**
- Produces: `screenshot.pick_monitor(cursor: tuple[int,int], monitors: list[dict]) -> dict` (reine Funktion), `screenshot.grab_monitor_under_cursor() -> PIL.Image.Image`.

- [ ] **Step 1: mss als Dependency**

In `requirements.txt` `mss>=9.0.0` ergänzen, in `pyproject.toml` dependencies ebenfalls. Dann `pip install mss`.

- [ ] **Step 2: Failing test pick_monitor (pure Logik)**

```python
# tests/test_screenshot.py
from voice_flow.screenshot import pick_monitor

# mss-Format: monitors[0] = virtual all-screen, ab [1] echte Monitore.
MONS = [
    {"left": 0, "top": 0, "width": 3840, "height": 1080},   # [0] virtuell
    {"left": 0, "top": 0, "width": 1920, "height": 1080},    # [1] links
    {"left": 1920, "top": 0, "width": 1920, "height": 1080}, # [2] rechts
]

def test_cursor_on_right_monitor():
    assert pick_monitor((2500, 400), MONS) == MONS[2]

def test_cursor_on_left_monitor():
    assert pick_monitor((100, 400), MONS) == MONS[1]

def test_cursor_outside_falls_back_to_first_real():
    assert pick_monitor((99999, 99999), MONS) == MONS[1]
```

Run: `pytest tests/test_screenshot.py -v`
Expected: FAIL (Modul fehlt).

- [ ] **Step 3: screenshot.py implementieren**

```python
# src/voice_flow/screenshot.py
from __future__ import annotations
import ctypes
import logging
from PIL import Image

log = logging.getLogger(__name__)


def get_cursor_pos() -> tuple[int, int]:
    pt = ctypes.wintypes.POINT() if hasattr(ctypes, "wintypes") else None
    import ctypes.wintypes
    pt = ctypes.wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)


def pick_monitor(cursor: tuple[int, int], monitors: list[dict]) -> dict:
    """Waehlt aus mss-Monitorliste den unter dem Cursor. monitors[0]=virtuell, ignorieren.
    Fallback: erster echter Monitor."""
    cx, cy = cursor
    for mon in monitors[1:]:
        if (mon["left"] <= cx < mon["left"] + mon["width"]
                and mon["top"] <= cy < mon["top"] + mon["height"]):
            return mon
    return monitors[1] if len(monitors) > 1 else monitors[0]


def grab_monitor_under_cursor() -> Image.Image:
    import mss
    with mss.mss() as sct:
        mon = pick_monitor(get_cursor_pos(), sct.monitors)
        shot = sct.grab(mon)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
```

- [ ] **Step 4: Test grün**

Run: `pytest tests/test_screenshot.py -v`
Expected: PASS (3 Tests).

- [ ] **Step 5: Manuelle Verifikation Grab**

```bash
python -c "from voice_flow.screenshot import grab_monitor_under_cursor; im=grab_monitor_under_cursor(); im.save('_shot_test.png'); print(im.size)"
```
Maus auf zweiten Monitor bewegen, erneut: PNG muss den **richtigen** Monitor zeigen, volle Auflösung (DPI-Check). `_shot_test.png` danach loeschen.

- [ ] **Step 6: Commit-Checkpoint.**

---

### Task 4: session.py (Bucket + bundle.md) + F7-Wiring + Lifecycle

**Files:**
- Modify: `src/voice_flow/config.py` (+ `screenshot_hotkey: str = "f7"`, `sessions_dir`)
- Create: `src/voice_flow/session.py`
- Modify: `src/voice_flow/app.py` (Session-Lifecycle + `on_screenshot_hotkey`)
- Modify: `src/voice_flow/cli.py` (F7-Hotkey registrieren)
- Test: `tests/test_session.py`

**Interfaces:**
- Consumes: `screenshot.grab_monitor_under_cursor()`.
- Produces:
  - `Session(base_dir: Path)` mit `.dir: Path`, `.add_screenshot(img) -> Path`, `.set_transcript(text: str) -> None`, `.shots: list[Path]`, `.build_bundle() -> Path`.
  - `session.new_session(base_dir: Path, now: str) -> Session` (now = vorformatierter Timestamp-String, injizierbar für Tests).
  - `app.on_screenshot_hotkey() -> None`.

- [ ] **Step 1: Failing test Session**

```python
# tests/test_session.py
from pathlib import Path
from PIL import Image
from voice_flow.session import new_session

def test_session_dir_and_bundle(tmp_path):
    s = new_session(tmp_path, "2026-06-27_14-03-22")
    assert s.dir == tmp_path / "2026-06-27_14-03-22"
    assert s.dir.exists()
    p1 = s.add_screenshot(Image.new("RGB", (10, 10), "red"))
    p2 = s.add_screenshot(Image.new("RGB", (10, 10), "blue"))
    assert p1.name == "shot_01.png" and p2.name == "shot_02.png"
    s.set_transcript("Das hier ist der Bug.")
    bundle = s.build_bundle()
    text = bundle.read_text(encoding="utf-8")
    assert "Das hier ist der Bug." in text
    assert "shot_01.png" in text and "shot_02.png" in text
    assert "—" not in text and "–" not in text  # keine KI-Striche
```

Run: `pytest tests/test_session.py -v`
Expected: FAIL (Modul fehlt).

- [ ] **Step 2: session.py implementieren**

```python
# src/voice_flow/session.py
from __future__ import annotations
import logging
from pathlib import Path
from PIL import Image

log = logging.getLogger(__name__)


class Session:
    def __init__(self, directory: Path):
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)
        self.shots: list[Path] = []
        self._transcript: str = ""

    def add_screenshot(self, img: Image.Image) -> Path:
        path = self.dir / f"shot_{len(self.shots) + 1:02d}.png"
        img.save(path)
        self.shots.append(path)
        log.info("SHOT  %s", path.name)
        return path

    def set_transcript(self, text: str) -> None:
        self._transcript = text or ""
        (self.dir / "transcript.md").write_text(self._transcript, encoding="utf-8")

    def build_bundle(self) -> Path:
        lines: list[str] = []
        if self._transcript:
            lines.append(self._transcript.strip())
            lines.append("")
        for shot in self.shots:
            lines.append(f"![{shot.name}]({shot.name})")
        bundle = self.dir / "bundle.md"
        bundle.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return bundle


def new_session(base_dir: Path, now: str) -> Session:
    return Session(base_dir / now)
```

- [ ] **Step 3: Test grün**

Run: `pytest tests/test_session.py -v`
Expected: PASS.

- [ ] **Step 4: config.py erweitern**

```python
# im @dataclass:
screenshot_hotkey: str = "f7"
# in load_config / oben:
from pathlib import Path as _P
sessions_dir: Path = _P.home() / "voice-flow" / "sessions"
```
(Default-Wert für `sessions_dir` als Field mit `default_factory`; in `load_config` per Env `VOICE_FLOW_SESSIONS_DIR` überschreibbar.)

- [ ] **Step 5: app.py — Session-Lifecycle**

```python
# app.py __init__: self.session = None  und  import datetime, threading-safe
# Beim Start (_start_recording): Session anlegen
def _ensure_session(self):
    if self.session is None:
        from voice_flow.session import new_session
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.session = new_session(self.config.sessions_dir, now)
    return self.session

def on_screenshot_hotkey(self) -> None:
    from voice_flow.screenshot import grab_monitor_under_cursor
    sess = self._ensure_session()
    try:
        img = grab_monitor_under_cursor()
        path = sess.add_screenshot(img)
        if self.overlay:
            self.overlay.show_info(f"Screenshot {len(sess.shots)} · {path.name}", 1400)
    except Exception as ex:
        log.error("Screenshot fehlgeschlagen: %s", ex)
```
In `_start_recording`: `self._ensure_session()`. In der Pipeline nach Cleanup: `if self.session: self.session.set_transcript(cleaned); self.session.build_bundle()`. Session-Reset (auf `None`) erst **nach** dem Dump (Phase 3) bzw. wenn der User explizit eine neue startet — Default: Session bleibt bis zum nächsten F8-Start offen, sodass F7 vor dem Reden auch geht.

- [ ] **Step 6: cli.py — F7 registrieren**

```python
keyboard.add_hotkey(cfg.screenshot_hotkey, app.on_screenshot_hotkey, suppress=False)
```

- [ ] **Step 7: Manuelle Verifikation E2E**

Tool starten. F8 (Aufnahme an), Maus auf Monitor 2, F7 zweimal, reden, F8 (stop). Prüfen: `~/voice-flow/sessions/<ts>/` enthält `shot_01.png`, `shot_02.png`, `transcript.md`, `bundle.md`; bundle.md zeigt Text + beide Bilder. Ordner-Screenshot als Beweis.

- [ ] **Step 8: Commit-Checkpoint.**

---

## Phase 2 — Annotate (Zeichnen, dann Screenshot)

### Task 5: annotate.py (transparentes Zeichen-Overlay + Toolbar + Fade + Composite)

**Design:** F6 öffnet auf dem Monitor unter der Maus ein transparentes, maus-aktives Vollbild-QWidget. Freihand-Striche (Liste von Polylinien) in wählbarer Farbe/Stärke, plus Pfeil + Rechteck. Loom-artige Mini-Toolbar (Farbe, Größe, Pfeil/Rechteck/Stift, Undo, Clear, „Shoot"). Auto-Fade: QTimer 3500ms, **resettet bei jedem Strich** (smart länger). Auf Shoot (F6 erneut / Enter / Toolbar-Button): Bildschirm via `mss` grabben, dieselben Vektor-Striche per Pillow/QPainter aufs PNG malen (Widget-Koords → Bild-Pixel mit DPI-Scale), in Session ablegen, Overlay schließen.

**Kritischer Constraint:** Das Overlay muss auf dem **bestehenden** Qt-Thread erzeugt werden (eine QApplication pro Prozess). Erzeugung/Teardown laufen über thread-safe Signals auf der `RecordingOverlay`-QApplication, NICHT als zweite App.

**Files:**
- Modify: `src/voice_flow/config.py` (+ `annotate_hotkey: str = "f6"`)
- Create: `src/voice_flow/annotate.py`
- Modify: `src/voice_flow/overlay_qt.py` (Signal `sig_open_annotate` auf dem Qt-Thread, das `annotate.AnnotateOverlay` erzeugt)
- Modify: `src/voice_flow/app.py` (`on_annotate_hotkey`, Callback der das fertige PNG in die Session legt)
- Modify: `src/voice_flow/cli.py` (F6 registrieren)
- Test: `tests/test_annotate_geometry.py`

**Interfaces:**
- Produces:
  - `annotate.map_point(widget_xy, mon_origin, scale) -> tuple[int,int]` (reine Koord-Mapping-Funktion).
  - `annotate.composite_strokes(img: Image.Image, strokes: list, scale: float, origin: tuple[int,int]) -> Image.Image` (reine Composite-Funktion, Pillow).
  - `annotate.AnnotateOverlay(QWidget)` mit Konstruktor `(monitor: dict, on_shoot: Callable[[Image.Image], None])`.
  - `RecordingOverlay.open_annotate(monitor: dict, on_shoot: Callable) -> None` (emittiert Signal in den Qt-Thread).

- [ ] **Step 1: Failing test Geometrie (pure Logik)**

```python
# tests/test_annotate_geometry.py
from PIL import Image
from voice_flow.annotate import map_point, composite_strokes

def test_map_point_applies_origin_and_scale():
    # Widget-Punkt (10,20) auf Monitor mit Ursprung (1920,0), DPI-Scale 1.5
    assert map_point((10, 20), (1920, 0), 1.5) == (1920 + 15, 0 + 30)

def test_composite_draws_without_error_and_keeps_size():
    img = Image.new("RGB", (200, 100), "white")
    strokes = [{"type": "pen", "color": (255,0,0), "width": 3,
                "points": [(5,5),(50,50),(80,20)]}]
    out = composite_strokes(img, strokes, scale=1.0, origin=(0,0))
    assert out.size == (200, 100)
    # Mind. ein roter Pixel auf der Linie
    assert any(px[0] > 200 and px[1] < 80 for px in out.getdata())
```

Run: `pytest tests/test_annotate_geometry.py -v`
Expected: FAIL (Modul fehlt).

- [ ] **Step 2: Pure-Logik in annotate.py implementieren** (map_point + composite_strokes via Pillow ImageDraw, Stift=line, Pfeil=line+Spitze, Rechteck=rectangle). Koordinaten werden mit `scale` multipliziert und um `origin` (Monitor-Ursprung im Bild=0,0 da pro-Monitor gegrabbt) verschoben. Vollständige Pillow-Implementierung, kein Platzhalter.

- [ ] **Step 3: Test grün.** Run: `pytest tests/test_annotate_geometry.py -v` → PASS.

- [ ] **Step 4: AnnotateOverlay (QWidget) bauen** — frameless, `WA_TranslucentBackground`, always-on-top, **ohne** `WindowTransparentForInput` (maus-aktiv), Geometrie = Monitor unter Cursor. `mousePressEvent/Move/Release` sammeln Striche; `paintEvent` zeichnet aktuelle Striche + Toolbar-Hinweis. Fade-`QTimer` (3500ms) startet/resettet in `mouseReleaseEvent`. `keyPressEvent`: Enter/F6 = Shoot, Esc = Abbrechen, Ctrl+Z = Undo. Shoot ruft `grab_monitor_under_cursor()`-Äquivalent für **diesen** Monitor + `composite_strokes` + `on_shoot(img)` + `self.close()`.

- [ ] **Step 5: Mini-Toolbar** als kleines Child-QWidget oben-mitte: Buttons Stift/Pfeil/Rechteck, 3 Farben, Strichstärke, Undo, Clear, „Foto" (Shoot). Klicks setzen den aktiven Tool-State, kein Fade während Maus über Toolbar.

- [ ] **Step 6: Thread-sicheres Öffnen** — in `overlay_qt.py` Signal `sig_open_annotate = pyqtSignal(object, object)` + Slot der `AnnotateOverlay(monitor, on_shoot)` auf dem Qt-Thread instanziiert und referenz-hält. `RecordingOverlay.open_annotate(monitor, on_shoot)` emittiert es.

- [ ] **Step 7: app + cli wiring**

```python
# app.py
def on_annotate_hotkey(self) -> None:
    from voice_flow.screenshot import get_cursor_pos, pick_monitor
    import mss
    with mss.mss() as sct:
        mon = pick_monitor(get_cursor_pos(), sct.monitors)
    sess = self._ensure_session()
    def on_shoot(img):
        sess.add_screenshot(img)
        if self.overlay:
            self.overlay.show_info(f"Markiert · Shot {len(sess.shots)}", 1400)
    if self.overlay:
        self.overlay.open_annotate(mon, on_shoot)
# cli.py
keyboard.add_hotkey(cfg.annotate_hotkey, app.on_annotate_hotkey, suppress=False)
```

- [ ] **Step 8: Manuelle Verifikation (die kritische)** — F6 auf Monitor 2: Overlay erscheint, Toolbar sichtbar. Zeichnen → Striche bleiben ~3.5s, weiteres Zeichnen verlängert. Pfeil/Rechteck/Farben testen. Enter → PNG landet in Session **mit eingebrannten Strichen**, an korrekter Pixel-Position (DPI-Check auf beiden Monitoren). Esc bricht ab (kein Shot). Beweis-Screenshots ablegen. **DPI-Fehler hier = Striche versetzt → vor „fertig" zwingend auf High-DPI-Monitor prüfen.**

- [ ] **Step 9: Commit-Checkpoint.**

---

## Phase 3 — Smart-Dump (kontext-bewusst ins fokussierte Fenster)

### Task 6: smart_paste.py (Target-Erkennung + Strategien) + F9-Wiring

**Design:** F9 (oder optional automatisch nach F8-Stop) erkennt das Vordergrund-Fenster und wählt:
- **vscode / plain** (`Code.exe`, Terminals, unbekannt): Clipboard = `bundle.md`-Text inkl. **absoluter Bild-Pfade** als Zeilen, dann Strg+V. (Bastians Haupt-Case: Claude Code liest die PNGs von Platte.)
- **rich** (`WINWORD`, `OUTLOOK`, Notion): CF_HTML mit base64-eingebetteten Bildern → ein Strg+V, Text+Bilder inline.
- **browser** (`chrome/msedge/firefox`): Text-Paste, dann Bilder einzeln (Bild→Clipboard→Strg+V→warten). Best-effort; Fallback = Bucket-Ordner öffnen.

**Files:**
- Modify: `requirements.txt`/`pyproject.toml` (+ `pywin32>=306`, nur für rich/browser-Clipboard)
- Modify: `src/voice_flow/config.py` (+ `dump_hotkey: str = "f9"`, `dump_auto_on_stop: bool = False`)
- Create: `src/voice_flow/smart_paste.py`
- Modify: `src/voice_flow/app.py` (`on_dump_hotkey`)
- Modify: `src/voice_flow/cli.py` (F9 registrieren)
- Test: `tests/test_smart_paste.py`

**Interfaces:**
- Produces:
  - `smart_paste.classify_target(exe_name: str) -> str` (reine Funktion → `"vscode"|"rich"|"browser"|"plain"`).
  - `smart_paste.foreground_exe() -> str` (ctypes: GetForegroundWindow → PID → Exe-Name).
  - `smart_paste.dump(session_dir: Path, transcript: str, shots: list[Path], target: str) -> None`.
  - `app.on_dump_hotkey() -> None`.

- [ ] **Step 1: Failing test classify_target (pure)**

```python
# tests/test_smart_paste.py
from voice_flow.smart_paste import classify_target

def test_vscode():     assert classify_target("Code.exe") == "vscode"
def test_word():       assert classify_target("WINWORD.EXE") == "rich"
def test_outlook():    assert classify_target("OUTLOOK.EXE") == "rich"
def test_chrome():     assert classify_target("chrome.exe") == "browser"
def test_edge():       assert classify_target("msedge.exe") == "browser"
def test_unknown():    assert classify_target("foobar.exe") == "plain"
```

Run: `pytest tests/test_smart_paste.py -v`
Expected: FAIL (Modul fehlt).

- [ ] **Step 2: classify_target + foreground_exe implementieren**

```python
# src/voice_flow/smart_paste.py
from __future__ import annotations
import ctypes, ctypes.wintypes, logging
from pathlib import Path

log = logging.getLogger(__name__)

_RICH = {"winword.exe", "outlook.exe", "onenote.exe"}
_BROWSER = {"chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe"}
_VSCODE = {"code.exe", "code - insiders.exe", "cursor.exe", "windowsterminal.exe", "wt.exe"}


def classify_target(exe_name: str) -> str:
    e = exe_name.lower()
    if e in _VSCODE:  return "vscode"
    if e in _RICH:    return "rich"
    if e in _BROWSER: return "browser"
    return "plain"


def foreground_exe() -> str:
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    hwnd = user32.GetForegroundWindow()
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    PROCESS_QUERY_LIMITED = 0x1000
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid.value)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(512)
        size = ctypes.wintypes.DWORD(512)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return Path(buf.value).name
        return ""
    finally:
        kernel32.CloseHandle(h)
```

- [ ] **Step 3: Test grün.** Run: `pytest tests/test_smart_paste.py -v` → PASS (6 Tests).

- [ ] **Step 4: dump-Strategien implementieren**
  - `_dump_plain_or_vscode`: `pyperclip.copy(transcript + "\n\n" + "\n".join(str(p) for p in shots))`, dann `keyboard.send("ctrl+v")`.
  - `_dump_rich`: CF_HTML-Fragment bauen (Text + `<img src="data:image/png;base64,…">` je Shot), via `win32clipboard` als `HTML Format` + Plaintext-Fallback setzen, dann Strg+V. (CF_HTML-Header mit korrekten StartHTML/EndHTML-Offsets.)
  - `_dump_browser`: Plaintext-Paste, dann pro Shot Bild als CF_DIB ins Clipboard (`win32clipboard`), Strg+V, `time.sleep(0.6)`. Bei Exception → `os.startfile(session_dir)` (Ordner auf für Drag-Drop) + Info-Overlay.
  - `dump(...)` dispatcht nach `target`.

- [ ] **Step 5: app + cli wiring**

```python
# app.py
def on_dump_hotkey(self) -> None:
    if not self.session or not self.session.shots and not getattr(self.session, "_transcript", ""):
        if self.overlay: self.overlay.show_info("Nichts zu dumpen", 1200)
        return
    from voice_flow import smart_paste
    target = smart_paste.classify_target(smart_paste.foreground_exe())
    smart_paste.dump(self.session.dir, getattr(self.session, "_transcript", ""),
                     self.session.shots, target)
    if self.overlay: self.overlay.show_info(f"Dump → {target}", 1400)
# cli.py
keyboard.add_hotkey(cfg.dump_hotkey, app.on_dump_hotkey, suppress=False)
```

- [ ] **Step 6: Manuelle Verifikation pro Ziel** — Session mit Text + 2 Shots bauen. (a) Fokus in VS Code/Claude Code → F9 → Text + absolute Pfade erscheinen, Pfade von Claude lesbar. (b) Fokus in Word → F9 → Text + beide Bilder inline. (c) Fokus claude.ai im Browser → F9 → Text + Bilder als Attachments (oder Fallback Ordner offen). Je ein Beweis-Screenshot.

- [ ] **Step 7: Commit-Checkpoint.**

---

## Phasen-Reihenfolge & Shipping

1. **Phase 0** (Task 1+2) zuerst: behebt Flocke + Toggle = sofort spürbar, kleiner Diff.
2. **Phase 1** (Task 3+4): Screenshots in Buckets, das neue Fundament.
3. **Phase 2** (Task 5): Zeichen-Tool, der größte Brocken.
4. **Phase 3** (Task 6): Smart-Dump, das fragilste Stück (Browser zuletzt, mit Fallback).

Jede Phase ist für sich lauffähig und liefert nutzbaren Mehrwert. Nach jeder Phase: frischer `critic`-Subagent auf den Diff (nur Diff + Auftrag), Findings als Mini-Fixes, dann manuelle Verifikation mit Screenshot-Beweis in `memory/_evidence/2026-06-27-voice-flow-v2/`.

## Offene Risiken (ehrlich)

- **Per-Monitor-DPI** (Phase 1 + 2): Cursor-Koords, mss-Grab und Qt-Widget-Koords können bei gemischtem DPI auseinanderlaufen → Striche/Crop versetzt. Muss auf einem High-DPI- + einem 100%-Monitor getestet werden. Ggf. `SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)` beim Start setzen.
- **`keyboard`-Lib + Toggle-Doppelfeuer**: per 300ms-Debounce abgefangen, aber auf echtem System verifizieren.
- **Browser-Auto-Attach** (Phase 3): timing-abhängig, claude.ai/ChatGPT-Paste kann zicken. Bewusst best-effort + Ordner-Fallback, keine 100%-Garantie.
- **Globale Hotkeys F6/F7/F9**: Kollision mit anderen Tools möglich. Alle in config überschreibbar.
