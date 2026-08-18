"""Geometrie + Hit-Test der Zeichen-Leiste, gebaut wie Lovables Annotation-Leiste.

18.08 Bastian: "die UI UX muss 1:1 wie bei Lovable sein". Lovables Leiste ist
bewusst karg: ein Stift-Knopf mit dem Wort "Annotation", dann Zurueck, Vor und
"Clear" — mehr nicht. Keine Werkzeug-Palette, keine Farbwahl (rot ist gesetzt),
und die drei rechten Knoepfe sind ausgegraut, solange nichts gezeichnet ist.
Die Formen entstehen nicht durch Werkzeugwahl, sondern beim Loslassen
(shape_snap) — genau das ist Lovables Trick.

Voice Flow braucht zwei Knoepfe mehr als Lovable, weil es kein Browser-Tab ist:
Aufnehmen (Screenshot mit den Markierungen) und Schliessen. Die sitzen abgesetzt
rechts, im selben Stil.

Bewusst OHNE Qt: Layout und Treffer-Erkennung sind reine Logik und damit
unit-getestet; annotate.py malt nur noch.
"""
from __future__ import annotations

from dataclasses import dataclass

from voice_flow.theme import PILL_HEIGHT, pill_rect_on

# Lovable zeichnet in Rot. Eine Farbe, keine Auswahl.
STROKE_COLOR: tuple[int, int, int] = (255, 69, 58)

BAR_HEIGHT = 44          # Hoehe der dunklen Leiste
BTN_H = 32               # Hoehe eines Knopfes
ICON_W = 36              # Breite eines reinen Icon-Knopfes
PAD_X = 10               # Innen-Polster links/rechts in der Leiste
GAP = 4                  # Abstand zwischen Knoepfen
SEP_GAP = 14             # Abstand an einer Gruppengrenze
LABEL_PAD = 14           # Polster links/rechts um eine Beschriftung
# Rechts an der Pille sitzt erst der Stift-Knopf (34px, Abstand 30), danach die
# Leiste — sonst liegen beide uebereinander.
GAP_TO_PILL = 30 + 34 + 10
CHAR_W = 7.2             # grobe Zeichenbreite fuer die Breitenrechnung


@dataclass(frozen=True)
class ToolbarItem:
    """Ein Knopf. kind in {tool, action}, value = konkrete Wahl."""
    kind: str
    value: object
    x: int
    y: int
    width: int
    height: int
    label: str | None = None
    icon: str | None = None          # Glyph-Name fuers Malen
    needs_strokes: bool = False      # ausgegraut, solange nichts gezeichnet ist
    needs_redo: bool = False         # ausgegraut, solange nichts zurueckgenommen wurde
    separator_before: bool = False

    @property
    def size(self) -> int:
        """Kantenlaenge fuer quadratische Knoepfe (Icon-Zeichnung)."""
        return self.height


# Reihenfolge wie bei Lovable, danach die zwei Voice-Flow-eigenen Knoepfe.
_SPEC: list[dict] = [
    {"kind": "tool", "value": "pen", "label": "Annotation", "icon": "pen"},
    {"kind": "action", "value": "undo", "icon": "undo", "needs_strokes": True,
     "separator_before": True},
    {"kind": "action", "value": "redo", "icon": "redo", "needs_redo": True},
    {"kind": "action", "value": "clear", "label": "Clear", "icon": "clear",
     "needs_strokes": True},
    {"kind": "action", "value": "shoot", "icon": "shoot", "separator_before": True},
    {"kind": "action", "value": "cancel", "icon": "cancel"},
]


def _item_width(spec: dict) -> int:
    label = spec.get("label")
    if not label:
        return ICON_W
    breite = int(len(label) * CHAR_W) + LABEL_PAD * 2
    if spec.get("icon"):
        breite += 20
    return breite


def build_toolbar(viewport_w: int, viewport_h: int,
                  nutzbar_unten: int | None = None) -> list[ToolbarItem]:
    """Knoepfe nebeneinander, RECHTS neben der Aufnahme-Pille.

    18.08 Bastian: "dann kommt es hier drunter, das soll rechts neben dem
    Aufnahme-Button sein". Passt die Leiste rechts nicht mehr aufs Bild, weicht
    sie nach unten-mittig aus, statt aus dem Bildschirm zu laufen.
    """
    breiten = [_item_width(spec) for spec in _SPEC]
    gesamt = sum(breiten)
    for i, spec in enumerate(_SPEC):
        if i > 0:
            gesamt += SEP_GAP if spec.get("separator_before") else GAP

    px, py, pw, ph = pill_rect_on(viewport_w, viewport_h, nutzbar_unten)
    start_x = px + pw + GAP_TO_PILL + PAD_X
    y = py + (ph - BTN_H) // 2
    if start_x + gesamt + PAD_X > viewport_w:      # kein Platz rechts
        start_x = max(PAD_X, (viewport_w - gesamt) // 2)
        y = max(PAD_X, py - PILL_HEIGHT - 28)

    items: list[ToolbarItem] = []
    x = start_x
    for i, spec in enumerate(_SPEC):
        if i > 0:
            x += SEP_GAP if spec.get("separator_before") else GAP
        items.append(ToolbarItem(
            kind=spec["kind"], value=spec["value"], x=x, y=y,
            width=breiten[i], height=BTN_H,
            label=spec.get("label"), icon=spec.get("icon"),
            needs_strokes=bool(spec.get("needs_strokes")),
            needs_redo=bool(spec.get("needs_redo")),
            separator_before=bool(spec.get("separator_before")),
        ))
        x += breiten[i]
    return items


def pill_rect(items: list[ToolbarItem]) -> tuple[int, int, int, int]:
    """(left, top, width, height) der dunklen Leiste hinter den Knoepfen."""
    left = min(it.x for it in items) - PAD_X
    right = max(it.x + it.width for it in items) + PAD_X
    top = min(it.y for it in items) - (BAR_HEIGHT - BTN_H) // 2
    return (left, top, right - left, BAR_HEIGHT)


def hit_test(point: tuple[int, int], items: list[ToolbarItem]) -> ToolbarItem | None:
    """Welcher Knopf liegt unter dem Punkt? None = daneben (also: zeichnen)."""
    px, py = point
    for it in items:
        if it.x <= px <= it.x + it.width and it.y <= py <= it.y + it.height:
            return it
    return None


def is_enabled(item: ToolbarItem, hat_striche: bool, hat_zurueckgenommenes: bool = False) -> bool:
    """Welche Knoepfe sind bedienbar?

    Zurueck und Clear brauchen Striche. "Vor" haengt dagegen am Zurueck-Stapel:
    gemessen 18.08. war es tot, weil nach dem Zurueck ja keine Striche mehr da
    waren — genau dann muss es aber gehen.
    """
    if item.needs_redo:
        return hat_zurueckgenommenes
    return hat_striche or not item.needs_strokes
