"""Headless wizard-render smoke test, as a regular pytest case.

Uses Qt's offscreen platform plugin (set in conftest.py) so the dialog never
appears on a real display. We auto-close any QDialog 200 ms after the wizard
starts, so the test terminates cleanly without a human in the loop.
"""
from __future__ import annotations

import pytest

# Skip cleanly on systems without PyQt6 — keeps the test suite green on bare
# Linux CI runners that haven't installed Qt yet.
PyQt6 = pytest.importorskip("PyQt6")


def test_wizard_renders_and_cancel_returns_none(tmp_path, monkeypatch):
    """The wizard's full dialog tree builds, runs the event loop, and cancels cleanly."""
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QDialog

    # Redirect APPDATA so any accidental write lands in tmp_path, not the real user dir.
    monkeypatch.setenv("APPDATA", str(tmp_path))

    # Reset cached voice_flow modules so USER_CONFIG_DIR picks up the new APPDATA
    import sys
    for mod in [m for m in sys.modules if m.startswith("voice_flow")]:
        del sys.modules[mod]

    from voice_flow.first_run import run_wizard

    app = QApplication.instance() or QApplication([])

    # Reject any open QDialog 200 ms after it shows
    QTimer.singleShot(
        200,
        lambda: [w.reject() for w in app.topLevelWidgets() if isinstance(w, QDialog)],
    )

    result = run_wizard()

    assert result is None, "Cancel-path must return None"
