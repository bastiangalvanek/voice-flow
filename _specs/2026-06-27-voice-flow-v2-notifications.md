# Voice Flow v2 — Notification System (Premium Toasts) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein premium, SaaS-grade Toast-Notification-System (Linear/Vercel-Stil) das dem User bei jedem Event Bescheid gibt (Aufnahme, Screenshot mit Thumbnail, Transkript fertig, Dump, Fehler) mit Icon, optionalem Thumbnail und optionalen Actions (Undo / Ordner / Kopieren / Dump) — ohne die bestehende Recording-Pille zu stören.

**Architecture:** Zwei getrennte UI-Systeme auf **einem** Qt-Thread (es gibt nur eine QApplication pro Prozess): (1) die bestehende `RecordingOverlay`-Pille = persistenter Recording-/Processing-HUD bottom-center, bleibt unverändert; (2) ein neuer `ToastManager` = transiente Event-Toasts top-right auf dem Monitor unter dem Cursor. Der ToastManager wird im bestehenden `_run_qt`-Thread der `RecordingOverlay` erzeugt und via thread-safe Qt-Signals gefüttert. Reine Logik (Kind→Style-Mapping, Stack-Positionen, Titel-Truncation) ist unit-getestet; Qt-Rendering wird manuell mit Screenshot-Beweis verifiziert.

**Tech Stack:** PyQt6 (bereits Dependency), Design-Tokens aus `overlay_qt.py` wiederverwendet, `QGuiApplication.screenAt(QCursor.pos())` für DPI-korrekte Monitor-Wahl, QPropertyAnimation für fade/slide.

## Global Constraints

- **Plattform:** Windows 11, Multi-Monitor + Per-Monitor-DPI. Toasts erscheinen auf dem Monitor unter dem Cursor zur Notify-Zeit.
- **Recording-Pille NIE clobbern.** Toasts sind ein eigenes Widget-System, eigene Position. `RecordingOverlay.show_recording/processing/success` bleiben funktional unverändert.
- **Toast erst nach echtem Ergebnis.** Ein Screenshot-Toast feuert NUR nachdem die PNG real gespeichert wurde, ein Dump-Toast NUR nach erfolgtem Dump. Nie spekulativ.
- **Click-through-Disziplin:** Toasts OHNE Action sind `WindowTransparentForInput` (null Störung). Toasts MIT Action sind interaktiv, aber `WA_ShowWithoutActivating` (stehlen keinen Fokus) und klein in der Ecke.
- **Keine KI-Striche** (em-/en-dash) in Toast-Texten. Mittelpunkt `·` oder ASCII-Hyphen.
- **Design-Konsistenz:** dieselben Tokens wie die Pille (`SURFACE_BASE` etc.), damit Pille + Toasts wie aus einer Hand wirken. Premium heißt: echte Drop-Shadows, abgerundete Ecken, Anti-Aliasing, smooth fade/slide, kein flackern.
- **Modul-Disziplin:** alles Toast-bezogene in `notifications.py` (+ ggf. `notifications_widget.py` wenn > ~300 Zeilen), NICHT in `overlay_qt.py` reinquetschen.
- **Lifecycle:** jeder Toast räumt sich selbst auf (`deleteLater()`), Stack reflowed bei Dismiss. Kein Widget-Leak bei 50 Screenshots/Session.

---

## File Structure

| Datei | Verantwortung | Status |
|---|---|---|
| `src/voice_flow/notifications.py` | `ToastKind`, `ToastSpec`, reine Helfer (`style_for`, `stack_positions`, `truncate`), `ToastManager` (Public API + Qt-Signals) | Create |
| `src/voice_flow/notifications_widget.py` | `ToastWidget` (QWidget: Icon, Titel, Subtitle, Thumbnail, Actions, fade/slide, hover-persist) — nur falls notifications.py > 300 Zeilen wird | Create (bei Bedarf) |
| `src/voice_flow/overlay_qt.py` | `RecordingOverlay._run_qt` erzeugt zusätzlich `ToastManager`; `RecordingOverlay.notify(...)` delegiert thread-safe | Modify |
| `src/voice_flow/app.py` | Event-Hooks: Screenshot/Transkript/Dump/Fehler → `self.overlay.notify(...)` | Modify |
| `tests/test_notifications.py` | Unit-Tests der reinen Helfer | Create |

---

## Task 1: notifications.py — Datentypen + reine Logik

**Files:**
- Create: `src/voice_flow/notifications.py`
- Test: `tests/test_notifications.py`

**Interfaces:**
- Produces:
  - `class ToastKind(str, Enum)`: `INFO`, `SUCCESS`, `ERROR`, `RECORDING`, `SCREENSHOT`, `TRANSCRIPT`, `DUMP`.
  - `@dataclass ToastSpec`: `kind: ToastKind`, `title: str`, `subtitle: str = ""`, `thumbnail_path: str | None = None`, `actions: list[tuple[str, Callable[[], None]]] = []`, `duration_ms: int = 4000`.
  - `style_for(kind: ToastKind) -> dict` → `{"accent": "#RRGGBB", "icon": "rec|cam|text|paste|check|warn|info"}`.
  - `truncate(text: str, n: int) -> str` (ASCII-Ellipsis-frei: nutzt `…`? Nein — kein KI-Strich nötig, `…` ist erlaubt; Titel hart auf n Zeichen + `…`).
  - `stack_positions(n: int, toast_h: int, screen: tuple[int,int,int,int], margin: int, gap: int) -> list[tuple[int,int]]` — reine Funktion: top-right Stack, neuester oben. `screen = (x, y, w, h)` der availableGeometry.

- [ ] **Step 1: Failing test stack_positions + style_for + truncate**

```python
# tests/test_notifications.py
from voice_flow.notifications import ToastKind, style_for, truncate, stack_positions

def test_style_for_known_kinds():
    s = style_for(ToastKind.SCREENSHOT)
    assert s["icon"] == "cam"
    assert s["accent"].startswith("#") and len(s["accent"]) == 7

def test_truncate_long_title():
    assert truncate("x" * 100, 40) == "x" * 40 + "…"
    assert truncate("kurz", 40) == "kurz"

def test_stack_positions_top_right_newest_on_top():
    # Screen 1920x1080 at origin, 2 Toasts, je 84px hoch, margin 20, gap 12, width 360
    screen = (0, 0, 1920, 1080)
    pos = stack_positions(2, 84, screen, margin=20, gap=12, width=360)
    # x identisch (rechtsbündig: 1920 - 360 - 20 = 1540)
    assert pos[0][0] == 1540 and pos[1][0] == 1540
    # neuester (index 0) oben: y0 < y1
    assert pos[0][1] == 20
    assert pos[1][1] == 20 + 84 + 12

def test_stack_positions_second_monitor_origin():
    screen = (1920, 0, 1920, 1080)  # Monitor 2
    pos = stack_positions(1, 84, screen, margin=20, gap=12, width=360)
    assert pos[0][0] == 1920 + 1920 - 360 - 20  # rechtsbündig auf Monitor 2
```

Run: `pytest tests/test_notifications.py -v`
Expected: FAIL (Modul fehlt).

- [ ] **Step 2: notifications.py reine Logik implementieren**

```python
# src/voice_flow/notifications.py (Auszug — reine Teile)
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

class ToastKind(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    ERROR = "error"
    RECORDING = "recording"
    SCREENSHOT = "screenshot"
    TRANSCRIPT = "transcript"
    DUMP = "dump"

@dataclass
class ToastSpec:
    kind: ToastKind
    title: str
    subtitle: str = ""
    thumbnail_path: str | None = None
    actions: list[tuple[str, Callable[[], None]]] = field(default_factory=list)
    duration_ms: int = 4000

_STYLE = {
    ToastKind.INFO:       {"accent": "#9B9BA3", "icon": "info"},
    ToastKind.SUCCESS:    {"accent": "#34D399", "icon": "check"},
    ToastKind.ERROR:      {"accent": "#FF453A", "icon": "warn"},
    ToastKind.RECORDING:  {"accent": "#FF453A", "icon": "rec"},
    ToastKind.SCREENSHOT: {"accent": "#F07320", "icon": "cam"},
    ToastKind.TRANSCRIPT: {"accent": "#FFB340", "icon": "text"},
    ToastKind.DUMP:       {"accent": "#34D399", "icon": "paste"},
}

def style_for(kind: ToastKind) -> dict:
    return _STYLE.get(kind, _STYLE[ToastKind.INFO])

def truncate(text: str, n: int) -> str:
    text = text.replace("\n", " ").strip()
    return text if len(text) <= n else text[:n] + "…"

def stack_positions(n, toast_h, screen, margin, gap, width):
    sx, sy, sw, sh = screen
    x = sx + sw - width - margin
    return [(x, sy + margin + i * (toast_h + gap)) for i in range(n)]
```

- [ ] **Step 3: Test grün.** Run: `pytest tests/test_notifications.py -v` → PASS (4 Tests).

- [ ] **Step 4: Commit-Checkpoint** (kein git-Repo — logischer Checkpoint).

---

## Task 2: ToastWidget (das premium Karten-Widget)

**Files:**
- Modify: `src/voice_flow/notifications.py` (oder neue `notifications_widget.py` falls > 300 Zeilen)

**Interfaces:**
- Consumes: `ToastSpec`, `style_for`.
- Produces: `build_toast_widget_class(...)` Factory (wie `_build_qt_class` in overlay_qt.py, verhindert Top-Level-Qt-Import) → `ToastWidget(QWidget)` mit `__init__(spec: ToastSpec, on_dismiss: Callable[["ToastWidget"], None])`, Methoden `animate_in()`, `dismiss()`, Property `desired_height -> int`.

**Design des Widgets (premium):**
- Breite 360px, dynamische Höhe (Titel + optional Subtitle + optional Action-Row). Surface `#15151A`→`#0B0B0F` Gradient, Radius 14, hairline-Border `rgba(255,255,255,0.08)`, Multi-Layer Drop-Shadow (wie Pille).
- Links: 8px Accent-Bar oder rundes Icon-Badge in Accent-Farbe (Icon je `kind`, vektorgemalt in `paintEvent` — rec=Kreis, cam=Kamera-Glyph, text=Zeilen, paste=Clipboard, check=Haken, warn=Dreieck, info=i).
- Mitte: Titel (Segoe UI Variable, 14px Medium, `#F2F2F5`), darunter Subtitle (11px, `#9B9BA3`).
- Rechts (optional): Thumbnail (48x48, Radius 8) wenn `thumbnail_path` gesetzt.
- Unten (optional): Action-Row — Text-Buttons (z.B. „Undo", „Ordner", „Kopieren", „Dump") in Accent/`#9B9BA3`, klickbar.
- Close-`×` oben-rechts (immer).
- Fade-in + slide-in von rechts (QPropertyAnimation auf `windowOpacity` + `pos`, QEasingCurve.OutCubic, ~180ms).
- Auto-Dismiss QTimer (`spec.duration_ms`), **pausiert bei Hover** (`enterEvent` stoppt Timer, `leaveEvent` startet ihn neu). Fehler-Toasts (`ERROR`) auto-dismissen langsamer (duration*2) oder gar nicht bis Klick.
- Click-through nur wenn `not spec.actions` (reine Info): dann `WindowTransparentForInput`. Mit Actions: interaktiv + `WA_ShowWithoutActivating`.

- [ ] **Step 1:** ToastWidget-Klasse via Factory bauen (vollständiges paintEvent mit Icon-Glyphen, Layout, Shadow; Animationen; Hover-Pause; Action-Buttons als child QPushButton oder gemalte Hotspots). Kein Platzhalter — echtes Widget.
- [ ] **Step 2: Manuelle Verifikation Einzel-Toast** — Test-Harness `python -m voice_flow.notifications --demo` der einen Demo-Toast je Kind zeigt. Screenshot je Kind, visuell prüfen: lesbar, Accent korrekt, Icon erkennbar, Thumbnail scharf, fade smooth. Beweis nach `memory/_evidence/2026-06-27-voice-flow-v2/toast-<kind>.png`.
- [ ] **Step 3: Critic-Subagent** auf das Widget (nur Diff + „premium Toast, kein clobber, lifecycle sauber").
- [ ] **Step 4: Commit-Checkpoint.**

---

## Task 3: ToastManager — Stack, Reflow, Thread-Safety, Integration in den Qt-Thread

**Files:**
- Modify: `src/voice_flow/notifications.py`
- Modify: `src/voice_flow/overlay_qt.py`

**Interfaces:**
- Produces:
  - `ToastManager` (lebt im Qt-Thread): `notify(spec: ToastSpec) -> None` (thread-safe via internem Signal), interne Liste aktiver `ToastWidget`, `_reflow()`, `_on_dismiss(widget)`.
  - `RecordingOverlay.notify(kind, title, subtitle="", thumbnail_path=None, actions=None, duration_ms=4000) -> None` — baut `ToastSpec`, emittiert thread-safe an den Manager.

**Design:**
- ToastManager hält `QObject` mit `sig_notify = pyqtSignal(object)` (ToastSpec). Slot erzeugt `ToastWidget` auf dem Qt-Thread, fügt ihn dem Stack hinzu, ruft `_reflow()` + `animate_in()`.
- `_reflow()`: berechnet `stack_positions(len(stack), ...)` für den Monitor unter dem Cursor (`screen = QGuiApplication.screenAt(QCursor.pos()) or primaryScreen()`, dann `availableGeometry()`), animiert jeden Toast an seine Soll-Position. Neuester oben.
- Max sichtbar (z.B. 5) — ältere überzählige werden sofort dismissed (kein endloser Stack). Bei vielen schnellen Screenshots optional **coalescing** (gleicher kind innerhalb 600ms → Titel-Update „3 Screenshots" statt 3 Karten) — als YAGNI erst bauen wenn es im echten Gebrauch nervt; im Plan NICHT erzwingen.
- `_on_dismiss(widget)`: aus Stack entfernen, `widget.deleteLater()`, `_reflow()`.
- `RecordingOverlay._run_qt`: nach `PillWidget`-Erzeugung `self._toasts = ToastManager(...)` anlegen (gleiche QApplication). `stop()` räumt auch Toasts ab.

- [ ] **Step 1:** ToastManager implementieren (Signal, Slot, Stack, Reflow, Monitor-Wahl via `screenAt(QCursor.pos())`, Max-Sichtbar-Cap mit `log()` wenn gekappt).
- [ ] **Step 2:** `RecordingOverlay.notify(...)` + Manager-Erzeugung in `_run_qt` + Teardown in `stop()`.
- [ ] **Step 3: Manuelle Verifikation Stack** — Demo: 4 Toasts schnell nacheinander → sauberer Stack top-right, neuester oben, kein Überlappen; einen dismissen → Rest reflowed smooth; Maus-Hover pausiert Timer. Auf Monitor 2 ausführen → Toasts auf Monitor 2 (nicht primary). DPI-Check. Beweis-Screenshot.
- [ ] **Step 4: Critic-Subagent** (Race-Conditions Stack-Mutation vom Signal-Thread, Leak-Check, clobbert die Pille nicht).
- [ ] **Step 5: Commit-Checkpoint.**

---

## Task 4: Event-Integration — die Toasts mit echten Events verdrahten

**Files:**
- Modify: `src/voice_flow/app.py`

**Abhängigkeit:** Screenshot-/Session-/Dump-Events stammen aus dem Haupt-Plan (`2026-06-27-voice-flow-v2-capture-annotate.md`, Phase 1/3). Was schon existiert, wird jetzt verdrahtet; die noch nicht gebauten Hooks werden an der exakten Stelle platziert sobald die Phase landet.

**Verdrahtung (nur nach echtem Ergebnis feuern):**
- **Aufnahme-Start** (`_start_recording`/`on_hotkey_press`): optional dezenter Toast — ODER weglassen, weil die Pille das schon zeigt (Default: weglassen, kein Doppel-Feedback).
- **Screenshot** (`on_screenshot_hotkey`, Phase 1, NACH `add_screenshot`):
  ```python
  self.overlay.notify(
      ToastKind.SCREENSHOT, f"Screenshot {len(sess.shots)}", path.name,
      thumbnail_path=str(path),
      actions=[("Ordner", lambda: _open_folder(sess.dir)),
               ("Undo", lambda p=path: _undo_shot(sess, p))],
  )
  ```
- **Transkript fertig** (Pipeline, NACH `append_transcript`):
  ```python
  self.overlay.notify(
      ToastKind.TRANSCRIPT, f"{word_count} Woerter", f"{total_s:.1f}s",
      actions=[("Kopieren", lambda t=cleaned: pyperclip.copy(t)),
               ("Dump", self.on_dump_hotkey)],
  )
  ```
- **Dump** (`on_dump_hotkey`, Phase 3, NACH erfolgreichem Dump): `notify(ToastKind.DUMP, f"Dump → {target}", ...)`.
- **Fehler** (nicht-fatale, statt nur `show_info`): `notify(ToastKind.ERROR, "Screenshot fehlgeschlagen", str(ex), duration_ms=8000)`.

- [ ] **Step 1:** Helfer `_open_folder(path)` (`os.startfile`) + `_undo_shot(sess, path)` (Datei löschen + aus `sess.shots` entfernen) in app.py.
- [ ] **Step 2:** Transkript-fertig-Toast verdrahten (existiert schon in der Pipeline) + Fehler-Pfade auf `notify(ERROR)` umstellen.
- [ ] **Step 3:** Screenshot-/Dump-Toasts an den in Phase 1/3 markierten Stellen (sobald gebaut).
- [ ] **Step 4: Manuelle E2E-Verifikation** — F8, F7 zweimal (zwei Screenshot-Toasts mit Thumbnail + Undo), reden, F8 (Transkript-Toast mit Kopieren/Dump), Dump (Dump-Toast). Undo testet (Shot weg). Beweis-Screenshots.
- [ ] **Step 5: Critic + Commit-Checkpoint.**

---

## Self-Review (gegen den Critical-Review-Befund)

- **Pille-Clobber:** gelöst — getrenntes Widget-System, eigene Position, Pille-API unangetastet. ✓
- **Multi-Monitor:** gelöst — `screenAt(QCursor.pos())`. ✓
- **Click-through vs Action:** gelöst — Info-Toasts click-through, Action-Toasts interaktiv + kein Fokus-Klau. ✓
- **State stimmt nicht:** gelöst — Toasts feuern nur nach echtem Ergebnis. ✓
- **Leak:** gelöst — `deleteLater()` + Reflow + Max-Cap. ✓
- **Über-Engineering (Coalescing):** bewusst als YAGNI markiert, erst bei echtem Nerv-Faktor. ✓

## Reihenfolge & Abhängigkeit

Dieser Plan ist **unabhängig** baubar (Task 1-3 brauchen nur die bestehende Pille). Task 4 verdrahtet Events — die Screenshot-/Dump-Hooks landen final wenn Phase 1/3 des Haupt-Plans stehen. Empfohlen: Toast-System (Task 1-3) als Nächstes, dann Phase 1 (Screenshots) bauen und dabei direkt Task-4-Screenshot-Toast mitnehmen.

## Offene Risiken (ehrlich)

- **Interaktive Toasts + globaler Tastatur-Hook:** `keyboard`-Lib läuft global; ein interaktiver Toast mit Fokus-Vermeidung (`WA_ShowWithoutActivating`) sollte Tastatur-Hooks nicht stören, aber auf echtem System verifizieren (klick auf „Undo" während F8-Hook aktiv).
- **Thumbnail-Last:** bei 50 Screenshots viele QPixmaps. Thumbnail auf 48px skaliert laden (nicht Vollbild im Speicher halten), Toast-Dismiss gibt Pixmap frei.
- **Animation-Performance:** mehrere gleichzeitige QPropertyAnimations bei Reflow — bei 5 Toasts unkritisch, aber nicht 20 gleichzeitig animieren (Max-Cap schützt).
