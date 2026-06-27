"""Overlay-Fassade: re-exportiert die PyQt6-Implementierung.

Geschichte:
- v1-4: tkinter-basiert. Limitationen: 1-bit transparency, kein Antialiasing,
  keine echten gradients, kein gaussian blur → "tkinter-widget-look".
- v5 (17.05): Switch auf PyQt6 (Bastian-Decision "lade alle skills die du brauchst").
  Echtes Antialiasing, gaussian-blur-shadows, smooth Bezier-wave, gradient fills.

Public API bleibt identisch — app.py muss nichts aendern.
"""
from voice_flow.overlay_qt import RecordingOverlay  # noqa: F401

__all__ = ["RecordingOverlay"]
