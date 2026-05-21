"""End-to-end wizard flow under Qt's offscreen platform plugin.

Renders the wizard, programmatically pastes an OpenAI key into the QLineEdit,
clicks the OK button, and verifies the .env file is written with the right
contents.

Exit codes:
  0 — full happy path verified
  1 — render or interaction failure
  2 — file contents wrong
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Redirect APPDATA so wizard writes the .env into a tmp dir, not the user's real one
tmp_dir = tempfile.mkdtemp(prefix="voice-flow-e2e-")
os.environ["APPDATA"] = tmp_dir
expected_env = Path(tmp_dir) / "voice-flow" / ".env"


def main() -> int:
    try:
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import (
            QApplication,
            QDialog,
            QDialogButtonBox,
            QLineEdit,
        )
    except Exception:
        traceback.print_exc()
        return 1

    # IMPORTANT: import voice_flow modules AFTER setting APPDATA so
    # USER_CONFIG_DIR picks up our tmp dir.
    try:
        # Force re-import of config in case it was already cached
        for mod in list(sys.modules):
            if mod.startswith("voice_flow"):
                del sys.modules[mod]

        from voice_flow.first_run import run_wizard
    except Exception:
        print("FAIL: voice_flow.first_run import")
        traceback.print_exc()
        return 1

    app = QApplication.instance() or QApplication(sys.argv)

    def simulate_user_input():
        """Fill the QLineEdit and click OK once the dialog is up."""
        for w in app.topLevelWidgets():
            if not isinstance(w, QDialog):
                continue
            line_edits = w.findChildren(QLineEdit)
            if not line_edits:
                print("FAIL: no QLineEdit found in wizard")
                w.reject()
                return
            # First QLineEdit = OpenAI key field
            line_edits[0].setText("sk-test-e2e-fake-key-1234567890")
            # Click OK on the button box
            buttons = w.findChildren(QDialogButtonBox)
            if not buttons:
                print("FAIL: no QDialogButtonBox found")
                w.reject()
                return
            ok_btn = buttons[0].button(QDialogButtonBox.StandardButton.Ok)
            if ok_btn is None:
                print("FAIL: no Ok button on the button box")
                w.reject()
                return
            ok_btn.click()

    QTimer.singleShot(300, simulate_user_input)

    try:
        result = run_wizard()
    except Exception:
        print("FAIL: run_wizard raised")
        traceback.print_exc()
        return 1

    print(f"wizard result: {result!r}")
    print(f"expected .env: {expected_env}")
    print(f".env exists:   {expected_env.exists()}")

    if not expected_env.exists():
        print("FAIL: wizard did not write .env after Ok click")
        return 2

    content = expected_env.read_text()
    print(f"\n--- written .env ---\n{content}\n--- end ---")
    if "OPENAI_API_KEY=sk-test-e2e-fake-key-1234567890" not in content:
        print("FAIL: expected key not in written file")
        return 2

    print("\nPASS: full wizard flow — render, input, click, write — works.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
