"""Zeichen-Leiste im Lovable-Stil: Layout, Treffer, Aktiv-/Aus-Zustand.

18.08 Bastian: "1:1 wie bei Lovable". Also genau die Knoepfe, die Lovable hat
(Annotation, Zurueck, Vor, Clear) plus die zwei, die Voice Flow braucht
(Aufnehmen, Schliessen) — und keine Werkzeug- oder Farbpalette mehr.
"""
from __future__ import annotations

from voice_flow.annotate_toolbar import (
    BAR_HEIGHT,
    STROKE_COLOR,
    ToolbarItem,
    build_toolbar,
    hit_test,
    is_enabled,
    pill_rect,
)


def _layout(w=1470, h=956):
    return build_toolbar(viewport_w=w, viewport_h=h)


def test_leiste_hat_genau_die_lovable_knoepfe():
    items = _layout()
    werte = [it.value for it in items]
    assert werte == ["pen", "undo", "redo", "clear", "shoot", "cancel"]
    # Keine Farbwahl mehr — Lovable zeichnet immer rot.
    assert not any(it.kind == "color" for it in items)
    assert STROKE_COLOR == (255, 69, 58)


def test_beschriftungen_wie_bei_lovable():
    items = {it.value: it for it in _layout()}
    assert items["pen"].label == "Annotation"
    assert items["clear"].label == "Clear"
    assert items["undo"].label is None       # nur Pfeil-Symbol
    assert items["redo"].label is None


def test_beschriftete_knoepfe_sind_breiter_als_symbol_knoepfe():
    items = {it.value: it for it in _layout()}
    assert items["pen"].width > items["undo"].width
    assert items["clear"].width > items["cancel"].width


def test_zurueck_vor_und_clear_sind_tot_ohne_striche():
    items = {it.value: it for it in _layout()}
    for wert in ("undo", "redo", "clear"):
        assert is_enabled(items[wert], hat_striche=False) is False
        assert is_enabled(items[wert], hat_striche=True) is True
    # Stift, Aufnehmen und Schliessen gehen immer.
    for wert in ("pen", "shoot", "cancel"):
        assert is_enabled(items[wert], hat_striche=False) is True


def test_leiste_liegt_rechts_neben_der_aufnahme_pille():
    """18.08 Bastian: "das soll rechts neben dem Aufnahme-Button sein"."""
    from voice_flow.theme import pill_rect_on

    items = _layout()
    assert len({it.y for it in items}) == 1, "alle Knoepfe auf einer Hoehe"
    px, py, pw, ph = pill_rect_on(1470, 956)
    left, top, width, height = pill_rect(items)
    assert left > px + pw, "Leiste beginnt erst rechts von der Pille"
    assert left - (px + pw) < 30, "aber direkt daneben, nicht irgendwo"
    assert height == BAR_HEIGHT
    # Auf gleicher Hoehe wie die Pille (Mitte auf Mitte, ein paar Pixel Toleranz).
    assert abs((top + height / 2) - (py + ph / 2)) <= 2
    assert left + width <= 1470, "darf nicht aus dem Bild laufen"


def test_leiste_weicht_nach_unten_mittig_aus_wenn_rechts_kein_platz_ist():
    items = build_toolbar(viewport_w=1000, viewport_h=700)
    px, py, pw, ph = __import__("voice_flow.theme", fromlist=["x"]).pill_rect_on(1000, 700)
    left, top, width, height = pill_rect(items)
    assert left >= 0 and left + width <= 1000
    assert top + height <= py, "dann sitzt sie ueber der Pille"


def test_treffer_auf_knopf_und_daneben():
    items = _layout()
    stift = items[0]
    assert hit_test((stift.x + 5, stift.y + 5), items) is stift
    assert hit_test((stift.x + stift.width // 2, stift.y + stift.height // 2), items) is stift
    # Weit oben im Bild = kein Knopf, dort wird gezeichnet.
    assert hit_test((700, 100), items) is None


def test_knoepfe_ueberlappen_sich_nicht():
    items = _layout()
    for a, b in zip(items, items[1:]):
        assert b.x >= a.x + a.width


def test_schmaler_bildschirm_laesst_die_leiste_im_bild():
    items = build_toolbar(viewport_w=900, viewport_h=600)
    left, top, width, height = pill_rect(items)
    assert left >= 0 and top >= 0
    assert isinstance(items[0], ToolbarItem)
