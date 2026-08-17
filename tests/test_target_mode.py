"""Ziel-Modus: zwei Modi, Marker-Form, Icons, Chip-Geometrie.

Reine Logik — kein Qt, kein Pasteboard, laeuft auf jeder Plattform.
"""
from __future__ import annotations

from voice_flow import target_mode as tm
from voice_flow.mode_chip import geometry_beside


def test_default_ist_claude_code():
    # 18.08 Bastian: kein Auto-Modus mehr, Claude Code ist der Start.
    assert tm.DEFAULT_MODE == tm.MODE_CLAUDE_CODE
    assert tm.normalize_mode(None) == tm.MODE_CLAUDE_CODE
    assert tm.normalize_mode("auto") == tm.MODE_CLAUDE_CODE   # Altwert aus settings.json
    assert tm.normalize_mode("quatsch") == tm.MODE_CLAUDE_CODE


def test_klick_schaltet_zwischen_den_zwei_modi():
    assert tm.next_mode(tm.MODE_CLAUDE_CODE) == tm.MODE_AI_WEB
    assert tm.next_mode(tm.MODE_AI_WEB) == tm.MODE_CLAUDE_CODE
    # Zweimal klicken landet wieder am Anfang.
    assert tm.next_mode(tm.next_mode(tm.MODE_CLAUDE_CODE)) == tm.MODE_CLAUDE_CODE


def test_beschriftung():
    assert tm.label(tm.MODE_CLAUDE_CODE) == "Claude Code"
    assert tm.label(tm.MODE_AI_WEB) == "AI-Web"


def test_jeder_modus_hat_ein_vorhandenes_icon():
    for mode in tm.MODE_CYCLE:
        pfad = tm.icon_path(mode)
        assert pfad is not None and pfad.exists(), mode
        assert pfad.suffix == ".png"


def test_marker_claude_code_traegt_den_pfad():
    marker = tm.capture_marker("/Users/b/voice-flow/sessions/x/shot_03.png", 3, tm.MODE_CLAUDE_CODE)
    assert marker == "(siehe shot_03.png im Bucket: /Users/b/voice-flow/sessions/x/shot_03.png)"


def test_marker_web_traegt_die_bildnummer_ohne_pfad():
    marker = tm.capture_marker("/Users/b/voice-flow/sessions/x/shot_03.png", 3, tm.MODE_AI_WEB)
    assert marker == "(siehe Bild 3)"
    assert "/Users" not in marker  # im Browser waere der Pfad wertlos


def test_chip_liegt_links_neben_der_pille_und_mittig():
    # Pille: x=600, y=900, 250x34. Chip 100x34 -> links daneben, gleiche Hoehe.
    assert geometry_beside((600, 900, 250, 34), 100, 34, gap=8) == (492, 900)


def test_chip_weicht_nach_rechts_aus_wenn_links_kein_platz_ist():
    x, _y = geometry_beside((10, 900, 250, 34), 100, 34, gap=8, screen_left=0)
    assert x == 268  # 10 + 250 + 8
