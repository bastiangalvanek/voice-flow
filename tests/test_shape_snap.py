"""Formerkennung: aus Gekritzel wird Kreis, Rechteck, Linie oder Pfeil.

Die Zuege hier sind absichtlich schlecht gezeichnet (Rauschen, nicht ganz
geschlossen, zittrige Linien) — genau so wie Bastian mit der Maus zeichnet.
"""
from __future__ import annotations

import math
import random

from voice_flow.shape_snap import snap


def _kreis(cx=200.0, cy=200.0, r=80.0, rauschen=6.0, luecke=0.12, punkte=60):
    zufall = random.Random(7)
    pts = []
    for i in range(punkte):
        a = (i / punkte) * (2 * math.pi) * (1 - luecke)
        wackel = zufall.uniform(-rauschen, rauschen)
        pts.append((cx + (r + wackel) * math.cos(a), cy + (r + wackel) * math.sin(a)))
    return pts


def _rechteck(x0=100.0, y0=100.0, x1=300.0, y1=220.0, rauschen=4.0):
    zufall = random.Random(3)
    ecken = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    pts = []
    for i in range(len(ecken) - 1):
        ax, ay = ecken[i]
        bx, by = ecken[i + 1]
        for s in range(12):
            t = s / 12
            pts.append((ax + (bx - ax) * t + zufall.uniform(-rauschen, rauschen),
                        ay + (by - ay) * t + zufall.uniform(-rauschen, rauschen)))
    pts.append(ecken[-1])
    return pts


def _linie(x0=50.0, y0=50.0, x1=400.0, y1=90.0, rauschen=3.0, punkte=30):
    zufall = random.Random(11)
    return [(x0 + (x1 - x0) * i / punkte + zufall.uniform(-rauschen, rauschen),
             y0 + (y1 - y0) * i / punkte + zufall.uniform(-rauschen, rauschen))
            for i in range(punkte + 1)]


def test_kritzelkreis_wird_ellipse():
    form, punkte = snap(_kreis())
    assert form == "ellipse"
    (x0, y0), (x1, y1) = punkte
    assert 110 < x0 < 135 and 265 < x1 < 290           # Box liegt um den Kreis (r=80 um 200)
    assert abs((x1 - x0) - (y1 - y0)) < 30            # ungefaehr rund


def test_zittrige_gerade_wird_linie():
    form, punkte = snap(_linie())
    assert form == "line"
    assert len(punkte) == 2
    assert punkte[0][0] < punkte[1][0]                 # Richtung bleibt erhalten


def test_viereck_wird_rechteck():
    form, punkte = snap(_rechteck())
    assert form == "rect"
    (x0, y0), (x1, y1) = punkte
    assert 90 < x0 < 110 and 290 < x1 < 310


def test_linie_mit_haken_am_ende_wird_pfeil():
    zug = _linie(x0=50, y0=300, x1=400, y1=300, rauschen=1.0, punkte=30)
    # Haken zurueck nach oben-links = gezeichnete Pfeilspitze.
    for i in range(1, 9):
        zug.append((400 - i * 6, 300 - i * 6))
    form, punkte = snap(zug)
    assert form == "arrow"
    assert len(punkte) == 2


def test_echtes_gekritzel_bleibt_freihand():
    zufall = random.Random(5)
    zug = [(100 + zufall.uniform(-60, 60), 100 + zufall.uniform(-60, 60)) for _ in range(40)]
    form, punkte = snap(zug)
    assert form == "pen"
    assert punkte == zug          # unveraendert weitergereicht


def test_winzige_zuege_bleiben_freihand():
    # Ein Klecks von 5 Pixeln soll kein Kreis werden.
    zug = [(10.0, 10.0), (12.0, 11.0), (13.0, 12.0), (12.0, 13.0), (10.0, 12.0), (10.0, 10.0)]
    assert snap(zug)[0] == "pen"
    assert snap([(1.0, 1.0), (2.0, 2.0)])[0] == "pen"   # zu wenige Punkte


def test_kreise_bleiben_kreise_ueber_groessen_und_zittern():
    """Regressionsschutz: mit der alten Schwelle wurde ein zittriger Kreis zum
    Rechteck (aufgefallen beim Rendern des Beweisbildes, nicht im Test)."""
    for r in (40, 70, 80, 120):
        for rauschen in (2, 6, 10):
            form, _ = snap(_kreis(cx=200, cy=200, r=float(r), rauschen=float(rauschen)))
            assert form == "ellipse", f"r={r} rauschen={rauschen} wurde {form}"


def test_rechtecke_bleiben_rechtecke_auch_krumm():
    for rauschen in (2, 4, 8, 12):
        form, _ = snap(_rechteck(rauschen=float(rauschen)))
        assert form == "rect", f"rauschen={rauschen} wurde {form}"
