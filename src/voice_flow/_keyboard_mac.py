"""macOS-Ersatz fuer die `keyboard`-Bibliothek (Windows/Linux-only).

Auf macOS bricht schon `import keyboard` mit einer CoreFoundation-Assertion ab
(__CFDataValidateRange). Dieses Modul bildet exakt die API-Teile nach, die
voice-flow benutzt, auf Basis von pynput:

    send, on_press_key, on_release_key, add_hotkey, is_pressed, unhook_all

Bewusst NICHT nachgebaut: alles was voice-flow nicht aufruft.

VORAUSSETZUNG: Bedienungshilfen-Recht. macOS liefert globale Tastenereignisse
nur an Programme, die unter Systemeinstellungen > Datenschutz & Sicherheit >
Bedienungshilfen freigegeben sind. Ohne das startet der Listener zwar, bekommt
aber nie ein Ereignis — die Hotkeys bleiben still. `permission_hint()` sagt,
ob Ereignisse ankommen.
"""

from __future__ import annotations

import logging
import threading
import time

from pynput import keyboard as _pk

log = logging.getLogger(__name__)

# ---------------------------------------------------------------- Namensmappen

# Modifier heissen bei `keyboard` anders als bei pynput. Links/rechts werden
# bewusst zusammengefasst — voice-flow unterscheidet sie nirgends.
_MODIFIER_ALIASES = {
    "ctrl": "ctrl", "control": "ctrl", "strg": "ctrl",
    "shift": "shift",
    "alt": "alt", "option": "alt", "alt gr": "alt", "altgr": "alt",
    # Auf Windows heisst die Taste "windows", auf dem Mac ist das Command.
    "windows": "cmd", "win": "cmd", "cmd": "cmd", "command": "cmd", "super": "cmd",
}

_SPECIAL_KEYS = {
    "esc": _pk.Key.esc, "escape": _pk.Key.esc,
    "space": _pk.Key.space, "tab": _pk.Key.tab,
    "enter": _pk.Key.enter, "return": _pk.Key.enter,
    "backspace": _pk.Key.backspace, "delete": _pk.Key.delete,
    "up": _pk.Key.up, "down": _pk.Key.down, "left": _pk.Key.left, "right": _pk.Key.right,
    "home": _pk.Key.home, "end": _pk.Key.end,
    "page up": _pk.Key.page_up, "page down": _pk.Key.page_down,
    **{f"f{i}": getattr(_pk.Key, f"f{i}") for i in range(1, 21)},
}

_MODIFIER_KEYS = {
    "ctrl": (_pk.Key.ctrl, _pk.Key.ctrl_l, _pk.Key.ctrl_r),
    "shift": (_pk.Key.shift, _pk.Key.shift_l, _pk.Key.shift_r),
    "alt": (_pk.Key.alt, _pk.Key.alt_l, _pk.Key.alt_r),
    "cmd": (_pk.Key.cmd, _pk.Key.cmd_l, _pk.Key.cmd_r),
}


def _normalise(name: str) -> str:
    """'F8' -> 'f8', 'Strg' -> 'ctrl', 'Windows' -> 'cmd'."""
    n = name.strip().lower()
    return _MODIFIER_ALIASES.get(n, n)


def _canonical(key) -> str | None:
    """pynput-Ereignis -> unser Namensschema. None wenn nicht abbildbar."""
    for canon, variants in _MODIFIER_KEYS.items():
        if key in variants:
            return canon
    for name, special in _SPECIAL_KEYS.items():
        if key is special:
            return name
    ch = getattr(key, "char", None)
    return ch.lower() if ch else None


# ---------------------------------------------------------------- Listener

_lock = threading.Lock()
_pressed: set[str] = set()
_press_handlers: dict[str, list] = {}
_release_handlers: dict[str, list] = {}
_hotkeys: list[tuple[frozenset[str], object]] = []
_hotkeys_armed: set[frozenset[str]] = set()
_listener: _pk.Listener | None = None
_events_seen = threading.Event()


def _fire(callbacks: list, key_name: str) -> None:
    """Callbacks duerfen den Listener-Thread nicht blockieren oder toeten."""
    for cb in list(callbacks):
        try:
            cb(_Event(key_name))
        except TypeError:
            try:
                cb()
            except Exception:
                log.exception("Hotkey-Callback fuer %r fehlgeschlagen", key_name)
        except Exception:
            log.exception("Hotkey-Callback fuer %r fehlgeschlagen", key_name)


class _Event:
    """Minimaler Ersatz fuer keyboard.KeyboardEvent — voice-flow liest nur .name."""

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name


def _on_press(key) -> None:
    _events_seen.set()
    name = _canonical(key)
    if name is None:
        return
    with _lock:
        _pressed.add(name)
        handlers = list(_press_handlers.get(name, ()))
        combos = [(c, cb) for c, cb in _hotkeys if c <= _pressed and c not in _hotkeys_armed]
        for c, _ in combos:
            _hotkeys_armed.add(c)
    _fire(handlers, name)
    for _, cb in combos:
        _fire([cb], name)


def _on_release(key) -> None:
    _events_seen.set()
    name = _canonical(key)
    if name is None:
        return
    with _lock:
        _pressed.discard(name)
        handlers = list(_release_handlers.get(name, ()))
        # Kombination gilt erst wieder als "neu gedrueckt", wenn sie zerfallen ist.
        for c in [c for c in _hotkeys_armed if not c <= _pressed]:
            _hotkeys_armed.discard(c)
    _fire(handlers, name)


# ---------------------------------------------------------------- Cmd+V-Haken

# 20.08 Bastian: einmal Cmd+V soll im AI-Web-Modus die ganze Kaskade ausloesen
# (erst Text, dann Bilder). Dafuer muss das native Cmd+V GESCHLUCKT werden
# koennen — pynput kann das auf macOS ueber darwin_intercept (laeuft als Event-
# Tap, gedeckt durch die ohnehin noetige Bedienungshilfen-Freigabe).
#
# Der Haken gibt True zurueck, wenn Voice Flow das Cmd+V uebernimmt. Jeder
# andere Fall — kein Haken gesetzt, falsche Tasten, Fehler im Haken — laesst
# das Ereignis UNBERUEHRT durch. Einfuegen darf nie kaputtgehen.
_cmd_v_hook = None
_KEYCODE_V = 9  # ANSI-Layout; gilt auch auf der deutschen Mac-Tastatur


def set_cmd_v_hook(callback) -> None:
    """callback() -> bool. True = Cmd+V schlucken (Kaskade laeuft an)."""
    global _cmd_v_hook
    _cmd_v_hook = callback


def _intercept(event_type, event):
    """Laeuft fuer JEDES Tastatur-Ereignis — der schnelle Pfad zaehlt."""
    if _cmd_v_hook is None:
        return event
    try:
        import Quartz

        if event_type != Quartz.kCGEventKeyDown:
            return event
        if Quartz.CGEventGetIntegerValueField(
                event, Quartz.kCGKeyboardEventKeycode) != _KEYCODE_V:
            return event
        flags = Quartz.CGEventGetFlags(event)
        if not flags & Quartz.kCGEventFlagMaskCommand:
            return event
        # Cmd+Shift+V (Wiederholen-Kuerzel), Cmd+Alt+V, Cmd+Ctrl+V: nicht unser Fall.
        if flags & (Quartz.kCGEventFlagMaskShift
                    | Quartz.kCGEventFlagMaskAlternate
                    | Quartz.kCGEventFlagMaskControl):
            return event
        if _cmd_v_hook():
            log.debug("Cmd+V uebernommen (Kaskade).")
            return None
    except Exception as ex:
        log.debug("Cmd+V-Haken-Fehler, Ereignis laeuft durch: %s", ex)
    return event


def _ensure_listener() -> None:
    global _listener
    if _listener is not None and _listener.running:
        return
    _listener = _pk.Listener(on_press=_on_press, on_release=_on_release,
                             darwin_intercept=_intercept)
    _listener.daemon = True
    _listener.start()
    log.debug("pynput-Listener gestartet")


# ---------------------------------------------------------------- Oeffentliche API


def on_press_key(key: str, callback, suppress: bool = False):
    """suppress wird auf macOS ignoriert — pynput kann Ereignisse nicht schlucken."""
    name = _normalise(key)
    with _lock:
        _press_handlers.setdefault(name, []).append(callback)
    _ensure_listener()
    _maybe_start_media_tap(name)
    return callback


def on_release_key(key: str, callback, suppress: bool = False):
    name = _normalise(key)
    with _lock:
        _release_handlers.setdefault(name, []).append(callback)
    _ensure_listener()
    _maybe_start_media_tap(name)
    return callback


def add_hotkey(hotkey: str, callback, suppress: bool = False, **_kw):
    combo = frozenset(_normalise(p) for p in hotkey.split("+") if p.strip())
    with _lock:
        _hotkeys.append((combo, callback))
    _ensure_listener()
    if len(combo) == 1:
        _maybe_start_media_tap(next(iter(combo)))
    return callback


def is_pressed(key: str) -> bool:
    with _lock:
        return _normalise(key) in _pressed


def unhook_all() -> None:
    global _listener
    with _lock:
        _press_handlers.clear()
        _release_handlers.clear()
        _hotkeys.clear()
        _hotkeys_armed.clear()
        _pressed.clear()
    if _listener is not None:
        try:
            _listener.stop()
        except Exception as ex:
            log.debug("Listener-Stop fehlgeschlagen: %s", ex)
        _listener = None


# ------------------------------------------------------- Sondertasten-Abfang
#
# 13.08 Bastian: F8/F7 gehoeren wieder der Musik (Play/Zurueck). Voice Flow
# nutzt auf dem Mac F5 (Aufnahme), F3 (Screenshot), F6 (Zeichnen). Diese drei
# Tasten haben ab Werk Systemfunktionen (Diktat, Mission Control, Nicht
# stoeren) — dieser Tap faengt sie VOR dem System ab und schluckt sie, aber
# nur solange die App laeuft und nur fuer tatsaechlich gebundene Tasten.
# Alle anderen Tasten (auch Play/Zurueck/Lautstaerke) laufen unveraendert durch.

_NS_SYSTEM_DEFINED = 14  # NSEventTypeSystemDefined

# Virtuelle Keycodes -> unser Namensschema. 96/97/99 sind die echten F-Codes
# (kommen bei gesetztem fnState oder Fn+Taste), 160 ist die Mission-Control-
# Sondertaste (bare F3). Diktat (bare F5) und Nicht-stoeren (bare F6) melden
# sich je nach macOS-Version mit Sondercodes — unbekannte Codes >= 130 werden
# deshalb geloggt, damit wir sie nachtragen koennen.
_KEYCODE_NAMES = {
    96: "f5",
    97: "f6",
    99: "f3",
    # Am 14.08. per Log-Messung auf Bastians MacBook Air bestimmt (der Nutzer
    # drueckte je einmal F3 und F6, das Log zeigt den Code pro Druck):
    160: "f3",   # bare F3 (Mission-Control-Taste)
    176: "f5",   # bare F5 (Diktat-Taste)
    178: "f6",   # bare F6 (Nicht-stoeren-Taste)
}


def _dispatch(name: str, key_down: bool) -> None:
    _events_seen.set()
    with _lock:
        if key_down:
            _pressed.add(name)
            handlers = list(_press_handlers.get(name, ()))
            combos = [(c, cb) for c, cb in _hotkeys
                      if c == frozenset({name}) and c not in _hotkeys_armed]
            for c, _cb in combos:
                _hotkeys_armed.add(c)
        else:
            _pressed.discard(name)
            handlers = list(_release_handlers.get(name, ()))
            combos = []
            _hotkeys_armed.discard(frozenset({name}))
    _fire(handlers, name)
    for _c, cb in combos:
        _fire([cb], name)


def _bound_names() -> set:
    with _lock:
        names = set(_press_handlers) | set(_release_handlers)
        for c, _cb in _hotkeys:
            if len(c) == 1:
                names |= set(c)
    return names


class _SpecialKeyTap:
    def __init__(self) -> None:
        self._started = False
        self._lock = threading.Lock()
        self._tap = None

    def ensure_started(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
        t = threading.Thread(target=self._run, daemon=True, name="special-key-tap")
        t.start()

    def _handle(self, proxy, type_, event, refcon):
        import Quartz

        if type_ in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
            Quartz.CGEventTapEnable(self._tap, True)
            return event
        try:
            if type_ in (Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp):
                code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
                name = _KEYCODE_NAMES.get(code)
                if name is None:
                    if code >= 130:
                        log.debug("Sondertaste unbekannt: keycode=%d (bitte melden)", code)
                    return event
                if name not in _bound_names():
                    return event
                if type_ == Quartz.kCGEventKeyDown:
                    log.debug("Sondertaste keycode=%d -> %s", code, name)
                _dispatch(name, type_ == Quartz.kCGEventKeyDown)
                return None  # schlucken — Systemfunktion (Diktat/Mission Control/DND) unterbleibt
            if type_ == _NS_SYSTEM_DEFINED:
                # Medientasten (Play etc.): NICHT mehr abfangen — nur loggen,
                # falls Diktat/DND hier statt als KeyDown ankommen sollten.
                from AppKit import NSEvent
                ns = NSEvent.eventWithCGEvent_(event)
                if ns is not None and ns.subtype() == 8:
                    data1 = ns.data1()
                    key_code = (data1 & 0xFFFF0000) >> 16
                    key_flags = data1 & 0xFFFF
                    key_down = ((key_flags & 0xFF00) >> 8) == 0x0A
                    if key_down and key_code not in (16, 17, 18, 19, 20, 0, 1, 2, 3, 7):
                        log.debug("NX-Sondertaste unbekannt: nx=%d (bitte melden)", key_code)
                return event
        except Exception:
            return event
        return event

    def _run(self) -> None:
        try:
            import Quartz

            mask = (
                Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
                | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
                | Quartz.CGEventMaskBit(_NS_SYSTEM_DEFINED)
            )
            self._tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap,
                Quartz.kCGHeadInsertEventTap,
                Quartz.kCGEventTapOptionDefault,
                mask,
                self._handle,
                None,
            )
            if self._tap is None:
                log.warning("Sondertasten-Tap nicht moeglich (Bedienungshilfen fehlen?)")
                return
            source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
            Quartz.CFRunLoopAddSource(
                Quartz.CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopCommonModes
            )
            Quartz.CGEventTapEnable(self._tap, True)
            log.debug("Sondertasten-Tap aktiv: F5/F3/F6 gehoeren Voice Flow, F7/F8 der Musik")
            Quartz.CFRunLoopRun()
        except Exception as ex:
            log.warning("Sondertasten-Tap gestorben: %s", ex)


_media_tap = _SpecialKeyTap()

_TAP_KEYS = frozenset({"f5", "f3", "f6"})


def _maybe_start_media_tap(key_name: str) -> None:
    if key_name in _TAP_KEYS:
        _media_tap.ensure_started()


_controller = _pk.Controller()


def send(combo: str) -> None:
    """Tastenkombination ausloesen.

    'ctrl+v' kommt aus dem Windows-Code und meint 'Einfuegen'. Auf dem Mac ist
    das Cmd+V — die woertliche Uebersetzung ctrl+v tut hier nichts. Deshalb
    wird ctrl bei reinen Buchstaben-Kombinationen auf cmd gedreht.
    """
    parts = [_normalise(p) for p in combo.split("+") if p.strip()]
    if "ctrl" in parts and all(len(p) == 1 or p in _MODIFIER_ALIASES.values() for p in parts):
        parts = ["cmd" if p == "ctrl" else p for p in parts]

    resolved = []
    for p in parts:
        if p in _MODIFIER_KEYS:
            resolved.append(_MODIFIER_KEYS[p][0])
        elif p in _SPECIAL_KEYS:
            resolved.append(_SPECIAL_KEYS[p])
        else:
            resolved.append(p)

    *mods, final = resolved
    for m in mods:
        _controller.press(m)
    try:
        _controller.press(final)
        _controller.release(final)
    finally:
        for m in reversed(mods):
            _controller.release(m)


def permission_hint(timeout: float = 1.5) -> bool:
    """True, wenn seit Listener-Start echte Tastenereignisse ankamen.

    False heisst fast immer: Bedienungshilfen-Recht fehlt. Der Aufrufer muss
    in dieser Zeit tatsaechlich eine Taste druecken, sonst ist das Ergebnis
    nicht aussagekraeftig.
    """
    _ensure_listener()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _events_seen.is_set():
            return True
        time.sleep(0.05)
    return False
