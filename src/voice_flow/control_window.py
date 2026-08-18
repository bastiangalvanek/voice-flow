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
import sys

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
#healthLabel { color: #9B9BA3; font-size: 11px; font-weight: 600; letter-spacing: 0.3px; }
#healthName { color: #C9C9D1; font-size: 12px; }
#healthValOk { color: #34D399; font-size: 12px; font-weight: 700; }
#healthValBad { color: #FF6B61; font-size: 12px; font-weight: 700; }
#healthFix {
    background: #1A1A20; color: #E6E6EA; border: 1px solid #3A3A45;
    border-radius: 8px; padding: 8px; font-size: 12px; font-weight: 600;
}
#healthFix:hover { border-color: #FFB340; color: #FFD08A; }
#signature { color: #6E6E7A; font-size: 11px; font-weight: 600; letter-spacing: 0.2px; padding-top: 2px; }
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
        # Beschriftung des Nachhol-Knopfs aus dem Arbeits-Thread. Qt-Widgets
        # duerfen NUR im Qt-Thread angefasst werden — sonst Absturz.
        sig_recover_text = pyqtSignal(str, bool)  # (Text, wieder klickbar)

        def __init__(self, on_quit, hotkey_label: str = "F5" if sys.platform == "darwin" else "F8"):
            super().__init__()
            self._on_quit = on_quit
            self._on_device_select = None  # callback(name) — gesetzt via set_devices
            self.setObjectName("root")
            self.setWindowTitle("Voice Flow")
            # 27.06: dritte Hotkey-Zeile (F6) -> +28px. + Mikrofon-Picker -> +62px.
            # +170px fuer das Feld "Freigaben & Transkripte" (19.08.).
            self.setMinimumSize(390, 566)
            self.resize(390, 566)

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

            # 19.08 Bastian: "einen Button, wo ich sehe: ist Transkript da, ja
            # oder nein — aehnlich wie im Bereich Videos". Und: "fixe die ganze
            # Kacke, dass das nicht andauernd wieder kommt". Beides loest dieses
            # Feld: der Zustand steht dauerhaft da, statt dass Dialoge aufpoppen.
            root.addLayout(self._build_health(
                QLabel, QFrame, QHBoxLayout, QVBoxLayout, QPushButton, Qt))

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

            # 18.08 Bastian: "developed with Herz by Bastian Galvanek" — steht in
            # beiden Fassungen (Mac und Windows) unten im Fenster.
            signatur = QLabel("developed with ❤️ by Bastian Galvanek")
            signatur.setObjectName("signature")
            signatur.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            root.addWidget(signatur)

            self.sig_status.connect(self._apply_status)
            self.sig_show.connect(self._do_show)
            self.sig_devices.connect(self._apply_devices)
            self.sig_recover_text.connect(self._apply_recover_text)
            self._apply_status("idle")

        def _do_show(self) -> None:
            self.show()
            self.raise_()
            self.activateWindow()

        # ── Freigaben & Transkripte ──────────────────────────────────
        def _build_health(self, QLabel, QFrame, QHBoxLayout, QVBoxLayout,
                          QPushButton, Qt):
            from PyQt6.QtCore import QTimer

            col = QVBoxLayout()
            col.setSpacing(7)
            titel = QLabel("FREIGABEN & TRANSKRIPTE")
            titel.setObjectName("healthLabel")
            col.addWidget(titel)

            self._health_rows = {}
            for schluessel, name in (("microphone", "Mikrofon"),
                                     ("accessibility", "Bedienungshilfen"),
                                     ("screen", "Bildschirmaufnahme"),
                                     ("transcripts", "Transkripte")):
                row = QHBoxLayout()
                row.setSpacing(9)
                punkt = QFrame()
                punkt.setFixedSize(9, 9)
                bez = QLabel(name)
                bez.setObjectName("healthName")
                wert = QLabel("…")
                row.addWidget(punkt)
                row.addWidget(bez)
                row.addStretch(1)
                row.addWidget(wert)
                col.addLayout(row)
                self._health_rows[schluessel] = (punkt, wert)

            self._fix_screen = QPushButton("Bildschirm-Freigabe reparieren")
            self._fix_screen.setObjectName("healthFix")
            self._fix_screen.setCursor(Qt.CursorShape.PointingHandCursor)
            self._fix_screen.clicked.connect(self._on_fix_screen)
            self._fix_screen.setVisible(False)
            col.addWidget(self._fix_screen)

            self._fix_transcripts = QPushButton("Fehlende Transkripte nachholen")
            self._fix_transcripts.setObjectName("healthFix")
            self._fix_transcripts.setCursor(Qt.CursorShape.PointingHandCursor)
            self._fix_transcripts.clicked.connect(self._on_fix_transcripts)
            self._fix_transcripts.setVisible(False)
            col.addWidget(self._fix_transcripts)

            # Alle 2,5 s nachsehen: gibt Bastian eine Freigabe im System frei,
            # springt die Zeile hier von selbst auf gruen — ohne Neustart, ohne
            # dass er raten muss, ob es gewirkt hat.
            self._health_timer = QTimer(self)
            self._health_timer.timeout.connect(self._refresh_health)
            self._health_timer.start(2500)
            self._refresh_health()
            return col

        def _refresh_health(self) -> None:
            try:
                from voice_flow import darwin_permissions as dp

                status = dp.permission_status()
            except Exception as ex:
                log.debug("Freigabe-Status nicht lesbar: %s", ex)
                status = {}

            for schluessel, text_ok, text_bad in (
                ("microphone", "Da", "Fehlt"),
                ("accessibility", "Da", "Fehlt"),
                ("screen", "Da", "Fehlt"),
            ):
                self._set_health(schluessel, status.get(schluessel, True),
                                 text_ok, text_bad)
            self._fix_screen.setVisible(not status.get("screen", True))

            offen = self._offene_transkripte()
            self._set_health("transcripts", offen == 0, "Alle da",
                             f"{offen} ohne Text")
            self._fix_transcripts.setVisible(offen > 0)

        def _set_health(self, schluessel: str, ok: bool, text_ok: str,
                        text_bad: str) -> None:
            eintrag = self._health_rows.get(schluessel)
            if eintrag is None:
                return
            punkt, wert = eintrag
            farbe = "#34D399" if ok else "#FF6B61"
            punkt.setStyleSheet(f"background:{farbe}; border-radius:4px;")
            wert.setText(text_ok if ok else text_bad)
            wert.setObjectName("healthValOk" if ok else "healthValBad")
            wert.setStyleSheet(f"color:{farbe}; font-size:12px; font-weight:700;")

        def _offene_transkripte(self) -> int:
            """Aufnahmen mit Ton, die noch keinen Text haben."""
            try:
                from voice_flow.recording_storage import list_pending_with_audio

                return len(list_pending_with_audio())
            except Exception as ex:
                log.debug("Offene Aufnahmen nicht zaehlbar: %s", ex)
                return 0

        def _on_fix_screen(self) -> None:
            """Toten Bildschirm-Eintrag loeschen und die Liste oeffnen.

            Hier — und NUR hier — darf sich ein Systemfenster oeffnen: weil
            Bastian selbst geklickt hat.
            """
            from voice_flow import darwin_permissions as dp

            # Reihenfolge zaehlt: erst den (moeglicherweise toten) Eintrag
            # loeschen, dann fragen. Ohne den Reset zeigt macOS den Dialog nicht
            # noch einmal, und ohne die Frage taucht Voice Flow nach dem Reset
            # gar nicht mehr in der Liste auf — dann kaeme man nie wieder rein.
            dp.repair_screen_capture()
            dp.request_screen_capture()
            dp.open_screen_capture_settings()
            self._fix_screen.setText(
                "Haken bei Voice Flow setzen, dann App neu starten")

        def _on_fix_transcripts(self) -> None:
            """Liegengebliebene Aufnahmen nachtraeglich verschriften."""
            import threading

            self._fix_transcripts.setEnabled(False)
            self._fix_transcripts.setText("Laeuft …")

            def arbeite() -> None:
                text = "Fehlende Transkripte nachholen"
                try:
                    from voice_flow.recover import nachholen

                    geschafft, fehler = nachholen(
                        fortschritt=lambda fertig, gesamt:
                        self.sig_recover_text.emit(f"{fertig} von {gesamt} …", False))
                    if fehler:
                        text = f"{geschafft} nachgeholt, {fehler} gescheitert"
                    elif geschafft:
                        text = f"{geschafft} nachgeholt"
                except Exception as ex:
                    log.warning("Nachtraegliche Verschriftung fehlgeschlagen: %s", ex)
                    text = "Fehlgeschlagen — siehe Protokoll"
                finally:
                    self.sig_recover_text.emit(text, True)

            threading.Thread(target=arbeite, daemon=True).start()

        def _apply_recover_text(self, text: str, klickbar: bool) -> None:
            self._fix_transcripts.setText(text)
            self._fix_transcripts.setEnabled(klickbar)

        def _hotkey_rows(self, record_key: str) -> list[tuple[str, str]]:
            # F9 (Senden) kommt sobald das Feature gebaut ist.
            return [
                (record_key, "Aufnahme starten / stoppen"),
                ("F3" if sys.platform == "darwin" else "F7", "Screenshot (Monitor unter der Maus)"),
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
            # 18.08: hiess frueher immer "Windows-Standard" — auf dem Mac schlicht
            # falsch. None = System-Standard, egal auf welchem System.
            combo.addItem("System-Standard", None)
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
