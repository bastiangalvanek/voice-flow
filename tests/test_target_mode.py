"""Ziel-Modus: Auflösung, Zyklus, Marker-Form, Chip-Geometrie.

Reine Logik — kein Qt, kein Pasteboard, laeuft auf jeder Plattform.
"""
from __future__ import annotations

from voice_flow import target_mode as tm
from voice_flow.mode_chip import geometry_beside


def test_feste_einstellung_gewinnt_ueber_vorder_app():
    # Explizit Claude Code, obwohl Chrome vorne ist -> Pfade, keine Bilder.
    assert tm.resolve_mode(tm.MODE_CLAUDE_CODE, "com.google.Chrome") == tm.MODE_CLAUDE_CODE
    # Und umgekehrt: AI-Web, obwohl das Terminal vorne ist.
    assert tm.resolve_mode(tm.MODE_AI_WEB, "com.apple.Terminal") == tm.MODE_AI_WEB


def test_auto_erkennt_browser_als_web():
    for bundle in ("com.google.Chrome", "com.apple.Safari", "company.thebrowser.Browser",
                   "com.openai.chat", "org.mozilla.firefox"):
        assert tm.resolve_mode(tm.SETTING_AUTO, bundle) == tm.MODE_AI_WEB, bundle


def test_auto_faellt_bei_terminal_und_unbekannt_auf_claude_code():
    # Terminal/Editor: Claude Code liest die Dateien selbst -> Pfade.
    for bundle in ("com.apple.Terminal", "com.googlecode.iterm2", "com.microsoft.VSCode",
                   "de.galvanek.voiceflow", None, ""):
        assert tm.resolve_mode(tm.SETTING_AUTO, bundle) == tm.MODE_CLAUDE_CODE, bundle


def test_zyklus_dreht_sich_und_faengt_muell_ab():
    assert tm.next_setting(tm.SETTING_AUTO) == tm.MODE_CLAUDE_CODE
    assert tm.next_setting(tm.MODE_CLAUDE_CODE) == tm.MODE_AI_WEB
    assert tm.next_setting(tm.MODE_AI_WEB) == tm.SETTING_AUTO
    assert tm.next_setting("quatsch") == tm.SETTING_AUTO


def test_chip_label_zeigt_bei_auto_das_ergebnis():
    assert tm.chip_label(tm.SETTING_AUTO, "com.google.Chrome") == "Auto · AI-Web"
    assert tm.chip_label(tm.SETTING_AUTO, "com.apple.Terminal") == "Auto · Claude Code"
    assert tm.chip_label(tm.MODE_AI_WEB, "com.apple.Terminal") == "AI-Web"


def test_marker_claude_code_traegt_den_pfad():
    marker = tm.capture_marker("/Users/b/voice-flow/sessions/x/shot_03.png", 3, tm.MODE_CLAUDE_CODE)
    assert marker == "(siehe shot_03.png im Bucket: /Users/b/voice-flow/sessions/x/shot_03.png)"


def test_marker_web_traegt_die_bildnummer_ohne_pfad():
    marker = tm.capture_marker("/Users/b/voice-flow/sessions/x/shot_03.png", 3, tm.MODE_AI_WEB)
    assert marker == "(siehe Bild 3)"
    assert "/Users" not in marker  # im Browser waere der Pfad wertlos


def test_chip_liegt_links_neben_der_pille_und_mittig():
    # Pille: x=600, y=900, 250x34. Chip 100x26 -> links daneben, vertikal zentriert.
    assert geometry_beside((600, 900, 250, 34), 100, 26, gap=8) == (492, 904)


def test_chip_weicht_nach_rechts_aus_wenn_links_kein_platz_ist():
    x, _y = geometry_beside((10, 900, 250, 34), 100, 26, gap=8, screen_left=0)
    assert x == 268  # 10 + 250 + 8
