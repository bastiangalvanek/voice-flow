"""Guthaben-leer-Anzeige: Pille + roter Toast mit Aufladen-Knopf, bei JEDEM Diktat.

20.08 Bastian: "das muss immer laufen". Vorher zeigte der Mac nur 8 s Pillen-Text
(das native Fehlerfenster ist Win32-only) und der Toast-Pfad existierte nicht.
Diese Tests nageln fest: Toast bei jedem betroffenen Diktat (keine Einmal-Sperre),
Knopf oeffnet die OpenAI-Billing-Seite, Pille meldet mit.
"""
from __future__ import annotations

import voice_flow.app as app_mod
from voice_flow.notifications import ToastKind


class _FakeOverlay:
    def __init__(self):
        self.toasts = []
        self.infos = []

    def notify(self, kind, title, subtitle="", thumbnail_path=None, actions=None,
               duration_ms=0):
        self.toasts.append({"kind": kind, "title": title, "sub": subtitle,
                            "actions": actions or []})

    def show_info(self, text, duration_ms=None):
        self.infos.append(text)


def _app_mit_overlay():
    """VoiceFlowApp ohne __init__ (kein Mikro/kein Netz) — nur die Anzeige-Logik."""
    app = object.__new__(app_mod.VoiceFlowApp)
    app.overlay = _FakeOverlay()
    return app


def test_toast_kommt_bei_jedem_diktat_nicht_nur_einmal():
    app = _app_mit_overlay()
    assert app._show_quota_error() is True
    assert app._show_quota_error() is True

    assert len(app.overlay.toasts) == 2, "Toast darf keine Einmal-Sperre haben"
    for toast in app.overlay.toasts:
        assert toast["kind"] is ToastKind.ERROR
        assert "Guthaben" in toast["title"]


def test_aufladen_knopf_oeffnet_openai_billing(monkeypatch):
    geoeffnet = []
    monkeypatch.setattr(app_mod.webbrowser, "open", geoeffnet.append)

    app = _app_mit_overlay()
    app._show_quota_error()

    actions = app.overlay.toasts[0]["actions"]
    assert [label for label, _ in actions] == ["OpenAI aufladen"]
    actions[0][1]()
    assert geoeffnet == [app_mod.OPENAI_BILLING_URL]
    assert "platform.openai.com" in app_mod.OPENAI_BILLING_URL


def test_pille_meldet_aufladen_und_gesicherte_aufnahme():
    app = _app_mit_overlay()
    app._show_quota_error()

    assert len(app.overlay.infos) == 1
    meldung = app.overlay.infos[0]
    assert "Guthaben" in meldung
    assert "gesichert" in meldung
    assert "Aufladen" in meldung


def test_toast_untertitel_passt_ins_toast_layout():
    """Ab ~44 Zeichen schneidet das Toast-System mit Ellipsis ab (16.08 gemessen)."""
    app = _app_mit_overlay()
    app._show_quota_error()
    assert len(app.overlay.toasts[0]["sub"]) <= 44


def test_ohne_overlay_kein_crash_und_kein_success_flag():
    app = object.__new__(app_mod.VoiceFlowApp)
    app.overlay = None
    assert app._show_quota_error() is False
