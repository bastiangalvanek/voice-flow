"""Headless wizard-render smoke test.

Imports first_run and builds the QDialog under Qt's offscreen platform plugin
so it never appears on a real display. After 100 ms we close the dialog
programmatically via QTimer.singleShot, so the script terminates cleanly
without a human in the loop.

Exit codes:
  0 — wizard rendered + closed cleanly
  1 — import or render failure
"""
from __future__ import annotations

import os
import sys
import traceback

# Force offscreen rendering BEFORE importing PyQt6
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Make sure we don't accidentally write a real .env if the dialog code paths
# get exercised — point USER_CONFIG_DIR at a tmp folder.
import tempfile
tmp_dir = tempfile.mkdtemp(prefix="voice-flow-smoke-")
os.environ["APPDATA"] = tmp_dir  # _user_config_dir reads APPDATA on win32


def main() -> int:
    try:
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication, QDialog
    except Exception:
        print("FAIL: PyQt6 import failed")
        traceback.print_exc()
        return 1

    try:
        # 1. Build the same dialog the wizard would build, but auto-close it.
        app = QApplication.instance() or QApplication(sys.argv)

        from voice_flow.first_run import run_wizard, write_env_file

        # Auto-close any top-level dialog 200 ms after it shows.
        def close_top_dialog():
            for w in app.topLevelWidgets():
                if isinstance(w, QDialog):
                    w.reject()  # treat as cancel

        QTimer.singleShot(200, close_top_dialog)

        result = run_wizard()
        print(f"PASS: wizard rendered + auto-closed; result={result!r}")

        # 2. Also exercise write_env_file directly to confirm the write path
        #    works against the same path logic used in production.
        from pathlib import Path
        target = Path(tmp_dir) / "smoke.env"
        written = write_env_file(
            openai_key="sk-smoke-test-key",
            target=target,
        )
        assert written.exists()
        assert "sk-smoke-test-key" in written.read_text()
        print(f"PASS: write_env_file wrote {written}")

        return 0
    except Exception:
        print("FAIL: smoke test crashed")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
