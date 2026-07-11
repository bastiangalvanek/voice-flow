"""Sichtbares Haupt-Fenster mit echtem Taskleisten-Button (Loom-Modell).

Warum noetig: die Pille ist ein Qt.Tool-Fenster und damit absichtlich AUS der
Taskleiste ausgeschlossen. Voice Flow hatte sonst nur ein Tray-Icon (im Win11-
Overflow versteckt). Dieses Fenster ist ein normales Top-Level-QWidget OHNE
Qt.Tool -> es bekommt einen Taskleisten-Button (sichtbar wenn aktiv, Rechtsklick
-> Schliessen = sauberer Quit).

Laeuft im SELBEN Qt-Thread wie die Pille (eine QApplication pro Prozess).
status_display() ist reine Logik (ohne Qt) und unit-getestet.
"""
from __future__ import annotations

import logging

from voice_flow.audio import clean_device_name
from voice_flow.logo_loader import resolve_icon_path, resolve_logo_path

log = logging.getLogger(__name__)


def status_display(state: str) -> tuple[str, str]:
    """(Label, Hex-Farbe) je App-State fuer Status-Punkt + Text."""
    table = {
        "idle": ("Bereit", "#34D399"),
        "recording": ("Aufnahme laeuft", "#FF453A"),
        "processing": ("Transkribiere", "#FFB340"),
        "error": ("Fehler", "#FF453A"),
    }
    return table.get(state, table["idle"])


_QSS = """
#root { background: #0E0E12; }
#brand { color: #F2F2F5; font-size: 16px; font-weight: 700; letter-spacing: 0.3px; }
#status { font-size: 14px; font-weight: 600; }
#legendKey {
    color: #C9C9D1; background: #1A1A20; border: 1px solid #2A2A33;
    border-radius: 6px; padding: 2px 8px; font-size: 11px; font-weight: 600;
}
#legendVal { color: #9B9BA3; font-size: 12px; }
#micLabel { color: #9B9BA3; font-size: 11px; font-weight: 600; letter-spacing: 0.3px; }
#micCombo {
    background: #1A1A20; color: #E6E6EA; border: 1px solid #2A2A33;
    border-radius: 8px; padding: 7px 10px; font-size: 12px;
}
#micCombo:hover { border-color: #3A3A45; }
#micCombo::drop-down { border: none; width: 22px; }
#micCombo QAbstractItemView {
    background: #16161B; color: #E6E6EA; border: 1px solid #2A2A33;
    selection-background-color: #2A2A33; outline: none;
}
#hint { color: #5C5C66; font-size: 11px; }
#quit {
    background: #1B1216; color: #FF6B61; border: 1px solid #3A2429;
    border-radius: 10px; padding: 11px; font-size: 13px; font-weight: 700;
}
#quit:hover { background: #2A161B; border-color: #FF453A; color: #FF8A82; }
#quit:pressed { background: #160E11; }
"""


def build_control_window_class():
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtGui import QIcon, QPixmap
    from PyQt6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

    class ControlWindow(QWidget):
        # thread-safe: set_status()/show/Device-Liste kann aus anderen Threads kommen
        sig_status = pyqtSignal(str)
        sig_show = pyqtSignal()
        sig_devices = pyqtSignal(object)  # payload: (devices, selected_name, on_select)

        def __init__(self, on_quit, hotkey_label: str = "F8"):
            super().__init__()
            self._on_quit = on_quit
            self._on_device_select = None  # callback(name) — gesetzt via set_devices
            self.setObjectName("root")
            self.setWindowTitle("Voice Flow")
            # 27.06: dritte Hotkey-Zeile (F6) -> +28px. + Mikrofon-Picker -> +62px.
            self.setMinimumSize(390, 372)
            self.resize(390, 372)

            logo = resolve_logo_path()
            # Taskleisten-Button: scharfe .ico bevorzugen, sonst logo.png.
            win_icon = resolve_icon_path() or logo
            if win_icon is not None:
                self.setWindowIcon(QIcon(str(win_icon)))
            self.setStyleSheet(_QSS)

            root = QVBoxLayout(self)
            root.setContentsMargins(24, 22, 24, 20)
            root.setSpacing(16)

            # Brand-Zeile: Flocke + "Voice Flow"
            brand = QHBoxLayout()
            brand.setSpacing(11)
            if logo is not None:
                pix = QPixmap(str(logo))
                if not pix.isNull():
                    icon = QLabel()
                    icon.setPixmap(pix.scaled(
                        26, 26, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation))
                    brand.addWidget(icon)
            brand_lbl = QLabel("Voice Flow")
            brand_lbl.setObjectName("brand")
            brand.addWidget(brand_lbl)
            brand.addStretch(1)
            root.addLayout(brand)

            # Status-Zeile: Punkt + Text
            status_row = QHBoxLayout()
            status_row.setSpacing(10)
            self._dot = QFrame()
            self._dot.setFixedSize(12, 12)
            self._status_lbl = QLabel()
            self._status_lbl.setObjectName("status")
            status_row.addWidget(self._dot)
            status_row.addWidget(self._status_lbl)
            status_row.addStretch(1)
            root.addLayout(status_row)

            # Hotkey-Legende (data-driven, leicht um F6/F9 erweiterbar).
            legend = QVBoxLayout()
            legend.setSpacing(7)
            for key, desc in self._hotkey_rows(hotkey_label):
                legend.addLayout(self._legend_row(QLabel, QHBoxLayout, key, desc))
            root.addLayout(legend)

            # Mikrofon-Auswahl (dynamisch befuellt via set_devices, thread-safe).
            mic_col = QVBoxLayout()
            mic_col.setSpacing(6)
            mic_lbl = QLabel("MIKROFON")
            mic_lbl.setObjectName("micLabel")
            self._mic_combo = QComboBox()
            self._mic_combo.setObjectName("micCombo")
            self._mic_combo.setCursor(Qt.CursorShape.PointingHandCursor)
            self._mic_combo.setEnabled(False)
            self._mic_combo.addItem("Wird geladen …")
            self._mic_combo.currentIndexChanged.connect(self._on_mic_changed)
            mic_col.addWidget(mic_lbl)
            mic_col.addWidget(self._mic_combo)
            root.addLayout(mic_col)

            root.addStretch(1)

            # Beenden-Button
            quit_btn = QPushButton("Voice Flow beenden")
            quit_btn.setObjectName("quit")
            quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            quit_btn.clicked.connect(self.close)  # -> closeEvent -> on_quit
            root.addWidget(quit_btn)

            hint = QLabel("Fenster schliessen (X) beendet Voice Flow.")
            hint.setObjectName("hint")
            hint.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            root.addWidget(hint)

            self.sig_status.connect(self._apply_status)
            self.sig_show.connect(self._do_show)
            self.sig_devices.connect(self._apply_devices)
            self._apply_status("idle")

        def _do_show(self) -> None:
            self.show()
            self.raise_()
            self.activateWindow()

        def _hotkey_rows(self, record_key: str) -> list[tuple[str, str]]:
            # F9 (Senden) kommt sobald das Feature gebaut ist.
            return [
                (record_key, "Aufnahme starten / stoppen"),
                ("F7", "Screenshot (Monitor unter der Maus)"),
                ("F6", "Markieren + Screenshot"),
            ]

        def _legend_row(self, QLabel, QHBoxLayout, key: str, value: str):
            row = QHBoxLayout()
            row.setSpacing(10)
            k = QLabel(key)
            k.setObjectName("legendKey")
            v = QLabel(value)
            v.setObjectName("legendVal")
            row.addWidget(k)
            row.addWidget(v)
            row.addStretch(1)
            return row

        # thread-safe Status-Update (aus app-Threads via Signal)
        def set_status(self, state: str) -> None:
            self.sig_status.emit(state)

        # thread-safe Mikrofon-Liste setzen (aus app-Thread via Signal).
        def set_devices(self, devices, selected_name, on_select) -> None:
            self.sig_devices.emit((list(devices), selected_name, on_select))

        def _apply_devices(self, payload) -> None:
            devices, selected_name, on_select = payload
            combo = self._mic_combo
            # Waehrend Neubefuellung KEIN Save ausloesen (currentIndexChanged feuert).
            self._on_device_select = None
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("Windows-Standard", None)  # None = Auto/Default
            select_row = 0
            for _idx, raw_name in devices:
                # Anzeige = sauberer Name, gespeichert/gematcht wird der Roh-Name.
                combo.addItem(clean_device_name(raw_name), raw_name)
                if selected_name and raw_name == selected_name:
                    select_row = combo.count() - 1
            combo.setCurrentIndex(select_row)
            combo.setEnabled(True)
            combo.blockSignals(False)
            self._on_device_select = on_select

        def _on_mic_changed(self, _index: int) -> None:
            if self._on_device_select is None:
                return
            name = self._mic_combo.currentData()  # Geraete-Name oder None
            try:
                self._on_device_select(name)
            except Exception as ex:
                log.warning("Mikrofon-Auswahl-Handler-Fehler: %s", ex)

        def _apply_status(self, state: str) -> None:
            label, color = status_display(state)
            self._dot.setStyleSheet(f"background:{color}; border-radius:6px;")
            self._status_lbl.setText(label)
            self._status_lbl.setStyleSheet(f"#status {{ color:{color}; }}")

        def closeEvent(self, event):
            # X-Button ODER Taskleisten-Rechtsklick -> Schliessen = sauberer Quit.
            log.info("ControlWindow geschlossen -> Quit.")
            try:
                if self._on_quit:
                    self._on_quit()
            except Exception as ex:
                log.warning("Quit-Handler-Fehler: %s", ex)
            event.accept()

    return ControlWindow
