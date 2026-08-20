"""nach_vorne() darf nie stumm nichts tun — im Zweifel raise_()."""
import sys

import pytest

from voice_flow.window_order import nach_vorne


class FakeWidget:
    def __init__(self, win_id=1):
        self._win_id = win_id
        self.raise_gerufen = 0

    def winId(self):
        if self._win_id is None:
            raise RuntimeError("kein Fenster")
        return self._win_id

    def raise_(self):
        self.raise_gerufen += 1


def test_ohne_mac_wird_raise_genutzt(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    w = FakeWidget()
    assert nach_vorne(w) is False
    assert w.raise_gerufen == 1


@pytest.mark.skipif(sys.platform != "darwin", reason="nur macOS")
def test_auf_mac_faellt_kaputtes_fenster_auf_raise_zurueck():
    w = FakeWidget(win_id=None)
    assert nach_vorne(w) is False
    assert w.raise_gerufen == 1
