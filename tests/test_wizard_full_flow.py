"""End-to-end wizard flow under Qt's offscreen platform plugin.

Pastes a fake OpenAI key, clicks the Ok button, and verifies the .env file
is written with the expected contents.
"""
from __future__ import annotations

import pytest

# Skip if PyQt6 isn't available (keeps suite green on bare-Linux CI)
PyQt6 = pytest.importorskip("PyQt6")


def test_wizard_paste_key_click_ok_writes_env(tmp_path, monkeypatch):
    """The full happy path: paste key → click Ok → .env written to APPDATA."""
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import (
        QApplication,
        QDialog,
        QDialogButtonBox,
        QLineEdit,
    )

    # Redirect APPDATA so the wizard writes the .env into tmp_path
    monkeypatch.setenv("APPDATA", str(tmp_path))

    # Reset cached voice_flow modules so USER_CONFIG_DIR picks up the new APPDATA
    import sys
    for mod in [m for m in sys.modules if m.startswith("voice_flow")]:
        del sys.modules[mod]

    from voice_flow.first_run import run_wizard

    expected_env = tmp_path / "voice-flow" / ".env"
    test_key = "sk-pytest-fake-key-1234567890"

    app = QApplication.instance() or QApplication([])

    def simulate_user_input():
        for w in app.topLevelWidgets():
            if not isinstance(w, QDialog):
                continue
            edits = w.findChildren(QLineEdit)
            assert edits, "wizard must contain at least one QLineEdit"
            edits[0].setText(test_key)
            boxes = w.findChildren(QDialogButtonBox)
            assert boxes, "wizard must contain a QDialogButtonBox"
            ok_btn = boxes[0].button(QDialogButtonBox.StandardButton.Ok)
            assert ok_btn is not None, "wizard must have an OK button"
            ok_btn.click()

    QTimer.singleShot(300, simulate_user_input)

    result = run_wizard()

    assert result == expected_env, f"wizard returned {result!r}, expected {expected_env!r}"
    assert expected_env.exists(), ".env must exist after Ok click"
    content = expected_env.read_text(encoding="utf-8")
    assert f"OPENAI_API_KEY={test_key}" in content, f"key not in written file: {content!r}"
