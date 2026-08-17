"""pytest configuration.

Runs ONCE before any test module is imported. We set QT_QPA_PLATFORM=offscreen
here so the wizard tests can render their PyQt6 dialog without a real display.

This is safe for all other tests too — they don't touch PyQt6.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure src/ is importable even when pytest is run from an unusual cwd
# or against a checkout where the package wasn't `pip install -e .`'d.
_repo_root = Path(__file__).resolve().parents[1]
_src = _repo_root / "src"
if _src.exists() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

# Render PyQt6 dialogs headlessly — no popup windows during the test run.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
