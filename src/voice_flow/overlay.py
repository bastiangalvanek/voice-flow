"""Overlay facade — re-exports the PyQt6 implementation.

Public API stays stable for app.py.
"""
from voice_flow.overlay_qt import RecordingOverlay  # noqa: F401

__all__ = ["RecordingOverlay"]
