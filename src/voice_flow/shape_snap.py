"""Aus Gekritzel wird beim Loslassen eine saubere Form.

18.08 Bastian ueber Lovables Annotation: "ich zeichne schlecht … lass los und
dann wird es so ein Kreis. Oder ein Pfeil." Genau das macht dieses Modul: es
schaut sich die Freihand-Punkte an und entscheidet, ob daraus eine Ellipse, ein
Rechteck, eine Linie oder ein Pfeil werden soll. Erkennt es nichts Klares,
bleibt der Strich wie gezeichnet — lieber Freihand behalten als etwas Falsches
hinzaubern.

Reine Mathematik, keine Qt-Abhaengigkeit, damit jede Regel unit-testbar ist.
"""
from __future__ import annotations

import math

Point = tuple[float, float]

# Ab wann gilt ein Zug als geschlossen: Abstand Start/Ende gemessen an der
# Diagonale der umschliessenden Box.
CLOSED_MAX_GAP = 0.30
# Wie stark duerfen die Punkte vom idealen Ellipsenrand abweichen (Anteil).
ELLIPSE_TOLERANCE = 0.22
# Wie nah muessen die Punkte am Rand der Box liegen, damit es ein Rechteck ist.
# GEMESSEN 18.08. ueber 12 Kreis- und 4 Rechteck-Varianten: Rechtecke landen bei
# 0.007 bis 0.036, Kreise nie unter 0.037. Zusaetzlich muss der Rechteck-Fehler
# klar kleiner sein als der Ellipsen-Fehler (Rechtecke: Faktor 0.05 bis 0.30,
# Kreise: nie unter 0.53) — mit nur einer der beiden Regeln wurde ein zittriger
# Kreis zum Rechteck.
RECT_TOLERANCE = 0.037
RECT_MUST_BEAT_ELLIPSE = 0.5
# Wie gerade muss ein Zug sein, damit er als Linie gilt: Weglaenge zu
# Luftlinie. 1.0 = perfekt gerade.
LINE_MAX_DETOUR = 1.12
# Ein Pfeil ist eine Linie mit Haken am Ende: die letzten Punkte knicken ab.
ARROW_MIN_HEAD_ANGLE = 25.0     # Grad
ARROW_MAX_HEAD_SHARE = 0.35     # Haken darf hoechstens so lang sein wie der Schaft
MIN_POINTS = 5
MIN_SIZE = 12.0                 # kleiner als das ist ein Klecks, kein Zeichen


def _dist(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _path_length(points: list[Point]) -> float:
    return sum(_dist(points[i], points[i + 1]) for i in range(len(points) - 1))


def bounding_box(points: list[Point]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _is_closed(points: list[Point], diagonal: float) -> bool:
    if diagonal <= 0:
        return False
    return _dist(points[0], points[-1]) / diagonal <= CLOSED_MAX_GAP


def _ellipse_error(points: list[Point], box: tuple[float, float, float, float]) -> float:
    """Mittlere relative Abweichung der Punkte vom Rand der Box-Ellipse.

    0 = alle Punkte liegen exakt auf der Ellipse. Werte ueber ~0.25 heissen:
    das war kein Kreis.
    """
    x0, y0, x1, y1 = box
    rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
    if rx <= 0 or ry <= 0:
        return 1.0
    cx, cy = x0 + rx, y0 + ry
    fehler = []
    for x, y in points:
        # Radius im Ellipsen-Massstab: 1.0 = genau auf dem Rand.
        r = math.hypot((x - cx) / rx, (y - cy) / ry)
        fehler.append(abs(r - 1.0))
    return sum(fehler) / len(fehler)


def _rect_error(points: list[Point], box: tuple[float, float, float, float],
                diagonal: float) -> float:
    """Mittlerer Abstand der Punkte zum Rand der Box, an der Diagonale gemessen.

    Beim Rechteck liegt jeder Punkt fast auf einer Kante -> nahe 0. Ein Kreis
    faellt hier durch, weil er zwischen den Ecken weit nach innen wandert.
    """
    x0, y0, x1, y1 = box
    if diagonal <= 0:
        return 1.0
    abstaende = []
    for x, y in points:
        abstaende.append(min(abs(x - x0), abs(x1 - x), abs(y - y0), abs(y1 - y)))
    return (sum(abstaende) / len(abstaende)) / diagonal


def _angle_between(a: Point, b: Point, c: Point) -> float:
    """Richtungsaenderung in b, in Grad (0 = geradeaus)."""
    v1 = math.atan2(b[1] - a[1], b[0] - a[0])
    v2 = math.atan2(c[1] - b[1], c[0] - b[0])
    d = math.degrees(abs(v2 - v1)) % 360
    return 360 - d if d > 180 else d


def _arrow_head(points: list[Point], laenge: float) -> bool:
    """Knickt der Zug am Ende scharf ab (also: Pfeilspitze gezeichnet)?"""
    if len(points) < 8 or laenge <= 0:
        return False
    # Punkt suchen, ab dem der Haken beginnt: rueckwaerts, bis der Anteil passt.
    rest = 0.0
    knick_index = len(points) - 1
    for i in range(len(points) - 1, 0, -1):
        rest += _dist(points[i - 1], points[i])
        if rest / laenge > ARROW_MAX_HEAD_SHARE:
            knick_index = i
            break
    if knick_index <= 1 or knick_index >= len(points) - 1:
        return False
    # Der Schaft (Anfang bis Knick) muss selbst gerade sein, sonst wird aus
    # jedem Gekritzel mit zufaelligem Knick am Ende ein Pfeil.
    schaft = points[:knick_index + 1]
    schaft_luft = _dist(schaft[0], schaft[-1])
    if schaft_luft <= 0 or _path_length(schaft) / schaft_luft > LINE_MAX_DETOUR:
        return False
    winkel = _angle_between(points[0], points[knick_index], points[-1])
    return winkel >= ARROW_MIN_HEAD_ANGLE


def snap(points: list[Point]) -> tuple[str, list[Point]]:
    """Freihand-Punkte -> (Form, kanonische Punkte).

    Rueckgabe-Formen:
      "ellipse" / "rect"  -> zwei Punkte: die Ecken der umschliessenden Box
      "line" / "arrow"    -> zwei Punkte: Anfang und Ende
      "pen"               -> unveraendert die Original-Punkte
    """
    if len(points) < MIN_POINTS:
        return ("pen", points)

    box = bounding_box(points)
    breite, hoehe = box[2] - box[0], box[3] - box[1]
    diagonale = math.hypot(breite, hoehe)
    if diagonale < MIN_SIZE:
        return ("pen", points)

    laenge = _path_length(points)
    luftlinie = _dist(points[0], points[-1])
    geschlossen = _is_closed(points, diagonale)

    if geschlossen:
        # Rund oder eckig? Beide Formen an derselben Box messen (siehe die
        # Schwellen oben, die aus einer Messreihe stammen).
        ellipse_fehler = _ellipse_error(points, box)
        rechteck_fehler = _rect_error(points, box, diagonale)
        if (rechteck_fehler <= RECT_TOLERANCE
                and rechteck_fehler < ellipse_fehler * RECT_MUST_BEAT_ELLIPSE
                and min(breite, hoehe) > MIN_SIZE):
            return ("rect", [(box[0], box[1]), (box[2], box[3])])
        if ellipse_fehler <= ELLIPSE_TOLERANCE:
            return ("ellipse", [(box[0], box[1]), (box[2], box[3])])
        return ("pen", points)

    # Offener Zug: gerade genug fuer Linie oder Pfeil?
    if luftlinie > 0 and laenge / luftlinie <= LINE_MAX_DETOUR:
        return ("line", [points[0], points[-1]])
    if _arrow_head(points, laenge):
        # Der Schaft endet dort, wo der Haken beginnt — Spitze bleibt das Ende.
        return ("arrow", [points[0], points[-1]])
    return ("pen", points)
