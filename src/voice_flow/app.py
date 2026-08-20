from __future__ import annotations

import logging
import threading
import time

from voice_flow.audio import AudioRecorder, list_input_devices
from voice_flow.audio_mute import SystemAudioMute
from voice_flow.cleanup import Cleaner
from voice_flow.config import Config
from voice_flow.gui_errors import show_error
from voice_flow.overlay import RecordingOverlay
from voice_flow.paste import paste_files_to_active_window, paste_to_active_window
from voice_flow.recording_storage import (
    RECORDINGS_DIR,
    archive_recording,
    list_pending_with_audio,
    mark_failed,
    mark_suspect,
    save_recording,
)
from voice_flow.settings import Settings
from voice_flow import target_mode
from voice_flow.sound import beep_error, beep_ready, beep_start, beep_stop
from voice_flow.transcript_history import append_transcript
from voice_flow.transcript_quality import is_suspect_transcription
from voice_flow.transcript_weave import weave_screenshot_markers
from voice_flow.transcription import Transcriber, TranscriberAuthError

log = logging.getLogger(__name__)


class VoiceFlowApp:
    """Controller: orchestriert Hotkey → Audio → Whisper → Cleanup → Paste.

    State-Machine: idle → recording → processing → idle.
    Locks verhindern Race-Conditions wenn Hotkey-Events ueberlappen.
    """

    STATE_IDLE = "idle"
    STATE_RECORDING = "recording"
    STATE_PROCESSING = "processing"

    def __init__(self, config: Config):
        self.config = config
        # Persistente Mikrofon-Wahl. UI-Dropdown schreibt hier rein, Recorder liest
        # bei JEDEM Start (Callable) → Auswahl wirkt live. Fallback-Kette in
        # resolve_input_device: UI-Wahl → .env-Override → Windows-Standard → erstes Mikro.
        self.settings = Settings()
        self.recorder = AudioRecorder(
            sample_rate=config.sample_rate,
            channels=config.channels,
            device=self._current_device,
            # Live-Mitschrift auf Platte: ohne sie lebt eine laufende Aufnahme nur
            # im RAM und ist bei Deadlock/Absturz weg (Vorfall 16.08.2026).
            spool_dir=RECORDINGS_DIR,
        )
        self.transcriber = Transcriber(
            api_key=config.openai_api_key,
            model=config.whisper_model,
        )
        self.cleaner = Cleaner(
            api_key=config.anthropic_api_key if config.enable_cleanup else None,
            model=config.cleanup_model,
            context=config.context,
        )
        self.state: str = self.STATE_IDLE
        self._state_lock = threading.Lock()
        self.tray = None  # wird vom CLI nach Konstruktion gesetzt
        # Auth-Error-Flag unter Lock (Critic P2-24: sonst race bei schnellem Double-F8).
        self._auth_error_shown = False
        # Eigener Hotkey-Down-Tracker, unabhaengig vom State (Critic P1-7).
        # Verhindert dass Windows-Typematic-Repeats erneute Press-Events feuern.
        self._hotkey_down = False
        # 27.06 Bastian: Toggle-Mode. Debounce gegen Doppelfeuer bei gehaltener Taste.
        self._last_toggle = 0.0
        # 27.06 Bastian: aktive Capture-Session (F7-Screenshots + Transkript-Bundle).
        # Bleibt ueber eine Aufnahme hinweg bestehen, bis die naechste startet.
        self.session = None
        # 27.06 Bastian: monotone Startzeit der laufenden Aufnahme. Erlaubt F7/F6
        # den Sprech-Offset (Sekunden seit Start) festzuhalten -> proportionale
        # Screenshot-Marker im Transkript.
        self._record_start: float | None = None
        # 18.08 Bastian: Ziel-App beim Aufnahme-Start festhalten. Zum Einfuege-
        # Zeitpunkt kann Voice Flow selbst vorne sein (Klick auf den Modus-Chip)
        # — dann waere die Auto-Erkennung blind. Diese ID ist der Rueckfall.
        self._target_bundle_id: str | None = None
        # Merker: der System-Dialog zur Bildschirmaufnahme kommt pro Lauf nur einmal.
        self._bildschirm_dialog_gezeigt = False

        # Floating Overlay (Wispr-Style) — laeuft in eigenem Tk-Thread
        self.overlay: RecordingOverlay | None = None
        if config.enable_overlay:
            try:
                self.overlay = RecordingOverlay(
                    always_visible=config.overlay_always_visible
                )
                if not self.overlay.available:
                    self.overlay = None
                    log.warning("Overlay nicht verfuegbar, laufe ohne floating UI.")
                else:
                    self.overlay.set_level_provider(lambda: self.recorder.current_level)
                    self._populate_mic_picker()
                    # Modus-Chip an der Pille: Klick schaltet um, Label zeigt
                    # sofort, wohin das naechste Diktat geht.
                    self.overlay.set_mode_click_handler(self.cycle_paste_mode)
                    self.overlay.set_annotate_click_handler(self.on_annotate_hotkey)
                    self._refresh_mode_chip()
            except Exception as ex:
                log.warning("Overlay-Init fehlgeschlagen: %s", ex)
                self.overlay = None

        # System-Audio-Mute (Wispr-Style: Musik/Meeting waehrend Diktat stumm)
        self.audio_mute: SystemAudioMute | None = None
        if config.enable_audio_mute:
            try:
                self.audio_mute = SystemAudioMute()
                if not self.audio_mute.available:
                    self.audio_mute = None
                    log.info("Audio-Mute nicht verfuegbar (pycaw fehlt oder kein Default-Output).")
                else:
                    log.info("Audio-Mute aktiv — System-Audio wird waehrend Recording stumm.")
            except Exception as ex:
                log.warning("Audio-Mute-Init fehlgeschlagen: %s", ex)
                self.audio_mute = None

    # ---------- Mikrofon-Auswahl ----------

    def _current_device(self) -> int | str | None:
        """Aktuell gewaehltes Mikro: UI-Wahl gewinnt, sonst .env-Override, sonst None."""
        return self.settings.audio_device or self.config.audio_device

    def _populate_mic_picker(self) -> None:
        """Fuellt das Dropdown im Control-Fenster mit allen vorhandenen Mikros."""
        try:
            devices = list_input_devices()
            self.overlay.set_device_controls(
                devices, self.settings.audio_device, self._on_mic_selected
            )
        except Exception as ex:
            log.warning("Mikrofon-Liste nicht ermittelbar: %s", ex)

    def _on_mic_selected(self, name: str | None) -> None:
        """Callback aus dem Dropdown — Wahl persistieren (wirkt beim naechsten F8)."""
        self.settings.set_audio_device(name)
        log.info("Mikrofon gewaehlt: %s", name or "Windows-Standard")

    # ---------- Ziel-Modus: Pfade (Claude Code) vs. Bilder (AI-Web) ----------

    def resolved_paste_mode(self) -> str:
        return self.settings.paste_mode

    def cycle_paste_mode(self) -> str:
        """Klick auf den Modus-Chip: Claude Code <-> AI-Web."""
        new_setting = target_mode.next_mode(self.settings.paste_mode)
        self.settings.set_paste_mode(new_setting)
        log.info("MODUS  %s", target_mode.label(new_setting))
        self._refresh_mode_chip()
        # Bewusst KEINE Fokus-Rueckgabe hier: gemessen 18.08. sprang der Fokus
        # dann bei jedem Klick zwischen Chip und Ziel-App hin und her, wodurch
        # der naechste Klick mal doppelt ankam und mal geschluckt wurde
        # (2 von 5). Der Fokus wird stattdessen EINMAL direkt vor dem Einfuegen
        # geradegezogen (_ensure_target_frontmost) — dort zaehlt er wirklich.
        return new_setting

    def _ensure_target_frontmost(self) -> None:
        """Vor dem Einfuegen sicherstellen, dass die Ziel-App vorne ist.

        Ein Klick auf den Modus-Chip holt Voice Flow nach vorne. Ohne diese
        Korrektur wuerde das Diktat in unser eigenes Fenster gehen.
        """
        if not self._target_bundle_id:
            return
        if target_mode.frontmost_bundle_id() != target_mode.own_bundle_id():
            return
        if target_mode.activate_bundle_id(self._target_bundle_id):
            log.info("FOKUS  Ziel-App %s zurueckgeholt.", self._target_bundle_id)
            time.sleep(0.35)  # macOS braucht einen Moment bis das Feld wieder Fokus hat

    def _refresh_mode_chip(self) -> None:
        if not self.overlay:
            return
        try:
            self.overlay.set_mode_chip(self.settings.paste_mode)
        except Exception as ex:
            log.warning("Modus-Chip nicht aktualisierbar: %s", ex)

    # ---------- Hotkey-Callbacks ----------

    def on_hotkey_press(self) -> None:
        # Hotkey-Down-Filter gegen Windows-Typematic-Repeats (Critic P1-7).
        # F8-halten feuert sonst alle ~50ms ein neues press-Event.
        with self._state_lock:
            if self._hotkey_down or self.state != self.STATE_IDLE:
                return
            self._hotkey_down = True
            self.state = self.STATE_RECORDING
            # Aufnahme-Start-Zeit atomar mit dem State setzen (Critic P2-A2): sonst
            # sieht ein sehr frueher F7 state=RECORDING aber _record_start=None und
            # verliert seinen Inline-Marker.
            self._record_start = time.monotonic()
            self._tray_set("recording")
            # 18.08: Ziel-App merken, BEVOR die Pille kommt — danach zeigt der
            # Chip an der Pille, wohin dieses Diktat geht (Pfade oder Bilder).
            vorne = target_mode.frontmost_bundle_id()
            # War Voice Flow selbst vorne (Klick auf Chip, Stift oder Fenster),
            # darf es sich NICHT als Ziel merken: am Ende des Diktats wuerde es
            # sich sonst selbst nach vorne holen — und macOS klappt dabei das
            # minimierte Fenster wieder auf.
            # 19.08 Bastian: "wenn ich es minimiere, soll es minimiert bleiben".
            self._target_bundle_id = target_mode.ziel_merken(
                vorne, target_mode.own_bundle_id())
            if self.overlay:
                self.overlay.show_recording()
                self._refresh_mode_chip()

        # 27.06 Bastian: Session sicherstellen, sodass eine laufende Aufnahme
        # und F7-Screenshots in denselben Bucket schreiben.
        self._ensure_session()

        # System-Audio muten BEVOR der Beep kommt (sonst hoert man den Beep nicht
        # selbst, aber Bastian hoert die Background-Musik durch sein Mikro-Recording)
        if self.audio_mute:
            self.audio_mute.mute()
        if self.config.enable_sound:
            beep_start()

        try:
            self.recorder.start()
            log.info("REC ▶  hotkey=%s", self.config.hotkey.upper())
        except Exception as ex:
            log.error("Recording-Start fehlgeschlagen: %s", ex)
            # Critic P0-5: Audio MUSS unmuted werden sonst bleibt System stumm
            if self.audio_mute:
                self.audio_mute.unmute()
            if self.config.enable_sound:
                beep_error()
            with self._state_lock:
                self.state = self.STATE_IDLE
                self._hotkey_down = False
                self._tray_set("error")
                if self.overlay:
                    self.overlay.hide()
                    # Klare Ursache statt stummem "Fehler": fast immer kein/deaktiviertes
                    # Mikro. Im Control-Fenster kann man oben ein anderes waehlen.
                    self.overlay.show_info(
                        "Mikrofon konnte nicht geoeffnet werden — anderes Mikro "
                        "im Voice-Flow-Fenster waehlen oder in Windows aktivieren.",
                        6000,
                    )

    def on_hotkey_release(self) -> None:
        with self._state_lock:
            # Hotkey-Down-Flag immer zuruecksetzen, egal in welchem State.
            self._hotkey_down = False
            if self.state != self.STATE_RECORDING:
                return
            self.state = self.STATE_PROCESSING
            self._tray_set("processing")
            if self.overlay:
                self.overlay.show_processing()

        if self.config.enable_sound:
            beep_stop()
        # System-Audio wieder aktivieren (User hoert Music/Meeting wieder)
        if self.audio_mute:
            self.audio_mute.unmute()

        try:
            wav = self.recorder.stop()
            duration = self.recorder.duration_seconds
        except Exception as ex:
            log.error("Recording-Stop fehlgeschlagen: %s", ex)
            with self._state_lock:
                self.state = self.STATE_IDLE
                self._tray_set("error")
                if self.overlay:
                    self.overlay.hide()
            return

        # CoreAudio haengt: die Aufnahme ist gerettet (Live-Mitschrift + RAM), aber
        # dieser Prozess bekommt kein Mikro mehr. Ehrlich sagen statt so tun als ginge
        # es weiter — der naechste F5 wuerde sonst still ins Leere laufen.
        if getattr(self.recorder, "audio_system_stuck", False) and self.overlay:
            self.overlay.show_info(
                "Audio-System von macOS haengt (Mikro-Wechsel waehrend der Aufnahme). "
                "Diese Aufnahme ist gesichert und wird noch transkribiert — "
                "danach Voice Flow bitte neu starten.",
                10000,
            )

        threading.Thread(
            target=self._process_pipeline,
            args=(wav, duration),
            daemon=True,
            name="voice-flow-pipeline",
        ).start()

    def on_hotkey_toggle(self) -> None:
        """F8 im Toggle-Modus: 1x druecken = Start, nochmal druecken = Stop.

        27.06 Bastian: kein Halten mehr. Reuse der bestehenden, getesteten
        Start/Stop-Pfade (on_hotkey_press/release). Typematic-Repeats werden
        bereits edge-getriggert in cli._setup_toggle_hotkey abgefangen (armed-Flag).
        Der 50ms-Backstop hier schuetzt die Methode nur gegen zwei echte Aufrufe
        im selben Augenblick; bewusste schnelle Stops (>50ms) gehen durch.
        """
        now = time.monotonic()
        with self._state_lock:
            if now - self._last_toggle < 0.05:
                return
            self._last_toggle = now
            current = self.state
        if current == self.STATE_IDLE:
            self.on_hotkey_press()
        elif current == self.STATE_RECORDING:
            self.on_hotkey_release()
        # PROCESSING: Pipeline laeuft noch — Toggle ignorieren.

    # ---------- Capture-Session / Screenshot ----------

    def _capture_offset(self) -> float | None:
        """Sekunden seit Aufnahme-Start, wenn gerade aufgenommen wird; sonst None.

        Ein Screenshot ausserhalb einer laufenden Aufnahme hat keinen Sprech-Offset
        -> None, kein Marker (er landet nur in shots, nicht in captures).
        """
        if self.state == self.STATE_RECORDING and self._record_start is not None:
            return time.monotonic() - self._record_start
        return None

    def _ensure_session(self):
        """Aktive Session zurueckgeben, bei Bedarf eine neue mit Timestamp-Bucket anlegen.

        Unter _state_lock (Critic P1): F7-Hook, F8-Hook und Pipeline-Thread koennen
        self.session sonst gleichzeitig lesen/setzen -> Lost-Update / falscher Bucket.
        new_session legt nur einen Ordner an, kein blockierendes I/O -> Lock unkritisch.
        """
        with self._state_lock:
            if self.session is None:
                import datetime

                from voice_flow.session import new_session
                now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                self.session = new_session(self.config.sessions_dir, now)
            return self.session

    def _bildschirm_freigabe_ok(self) -> bool:
        """Vor jedem Screenshot: darf die App ueberhaupt den Bildschirm sehen?

        Fehlt die Freigabe, liefert macOS still ein Bild von Hintergrund und
        eigenen Fenstern - der Nutzer haelt es fuer einen echten Screenshot.
        Also lieber laut sagen und die Einstellungen oeffnen.
        """
        import sys as _sys

        if _sys.platform != "darwin":
            return True
        from voice_flow import darwin_permissions as dp

        if dp.screen_capture_ok():
            return True
        log.warning("Bildschirmaufnahme nicht erlaubt - Screenshot zeigt nur den Hintergrund.")
        # 19.08 Bastian: "bei jedem F5/F3 kommt das Fenster hoch obwohl ich es
        # minimiert habe". Ursache war genau hier: open_screen_capture_settings()
        # bei JEDEM Tastendruck. Das oeffnet nicht nur die Systemeinstellungen,
        # es AKTIVIERT dabei auch Voice Flow — und macOS holt ein minimiertes
        # Fenster wieder hervor.
        # Ab jetzt: nur ein Hinweis in der Pille. Weder Systemeinstellungen noch
        # System-Dialog werden aus einem Tastendruck heraus geoeffnet. Freigeben
        # laeuft ausschliesslich ueber den Knopf im Voice-Flow-Fenster.
        if self.overlay:
            self.overlay.show_info(
                "Bildschirmaufnahme nicht erlaubt — im Voice-Flow-Fenster auf "
                "\u201eFreigabe reparieren\u201c druecken.",
                6000,
            )
        return False

    def on_screenshot_hotkey(self) -> None:
        """F7: Monitor unter der Maus grabben, in den Session-Bucket legen, Toast zeigen."""
        from voice_flow.screenshot import grab_monitor_under_cursor

        if not self._bildschirm_freigabe_ok():
            return
        sess = self._ensure_session()
        try:
            img = grab_monitor_under_cursor()
            path = sess.add_screenshot(img, offset=self._capture_offset())
        except Exception as ex:
            log.error("Screenshot fehlgeschlagen: %s", ex)
            if self.overlay:
                from voice_flow.notifications import ToastKind
                self.overlay.notify(
                    ToastKind.ERROR, "Screenshot fehlgeschlagen", str(ex), duration_ms=6000
                )
            return
        if self.overlay:
            from voice_flow.notifications import ToastKind
            self.overlay.notify(
                ToastKind.SCREENSHOT, f"Screenshot {len(sess.shots)}", path.name,
                thumbnail_path=str(path),
                actions=[("Ordner", lambda d=sess.dir: _open_folder(d))],
            )

    def on_escape(self) -> None:
        """ESC: nur die Zeichen-Ebene schliessen, sonst nichts.

        Der Listener beobachtet ESC bloss (suppress=False) — ESC wirkt in jeder
        anderen App unveraendert weiter.
        """
        if not self.overlay:
            return
        try:
            if self.overlay.close_annotate():
                log.debug("ESC: Zeichen-Ebene geschlossen.")
        except Exception as ex:
            log.debug("ESC-Behandlung fehlgeschlagen: %s", ex)

    def _kaskade_einfuegen(self, text: str, shots: list, captures: list,
                           duration: float, mode: str) -> tuple[str, int]:
        """Text einfuegen, danach — nur im AI-Web-Modus — die Bilder.

        Zwei getrennte Vorgaenge, weil Chrome den Text verwirft, sobald Dateien
        mit auf der Zwischenablage liegen (gemessen 18.08.: text="" sobald
        Dateien dabei sind). Deshalb erst die Worte, dann die Bilder.

        ALLE Bilder gehen in EINEM Vorgang mit — Chrome nimmt eine Mehrfach-
        Dateiauswahl als mehrere Anhaenge an. Es gibt keine Obergrenze im
        Programm; zwanzig Screenshots landen genauso in einem Rutsch wie zwei.

        Rueckgabe: (eingefuegter Text, Anzahl eingefuegter Bilder)
        """
        shot_index = {str(p): i + 1 for i, p in enumerate(shots)}
        marker = [(off, target_mode.capture_marker(p, shot_index.get(p, 1), mode))
                  for off, p in captures]
        final_text = weave_screenshot_markers(text, marker, duration) if marker else text

        paste_to_active_window(
            final_text, restore_clipboard=self.config.enable_clipboard_restore)

        pasted_images = 0
        if mode == target_mode.MODE_AI_WEB and shots:
            try:
                pasted_images = paste_files_to_active_window(shots)
                log.info("PASTE  ✓ %d Bild(er) als Dateien eingefuegt.", pasted_images)
            except Exception as ex:
                log.error("Bilder-Einfuegen fehlgeschlagen: %s", ex)
                if self.overlay:
                    self.overlay.show_info(
                        f"Text ist drin, Bilder nicht ({ex}). "
                        "Ordner ueber den Toast oeffnen und manuell ziehen.",
                        6000,
                    )
        # Cmd+V-Kaskade scharf stellen: nur wenn die Zwischenablage jetzt
        # UNSERE Bilder traegt, darf ein spaeteres Cmd+V die Kaskade ausloesen.
        from voice_flow import smart_paste

        self._clipboard_stand = (smart_paste.clipboard_stand()
                                 if mode == target_mode.MODE_AI_WEB else None)
        return final_text, pasted_images

    def on_cmd_v(self) -> bool:
        """Vom Tastatur-Tap gerufen. True = wir uebernehmen dieses Cmd+V.

        Muss SOFORT zurueckkehren (laeuft im Event-Tap, jede Verzoegerung
        bremst systemweit das Tippen) — die Arbeit passiert im Thread.
        Im Zweifel False: das native Einfuegen darf nie kaputtgehen.
        """
        try:
            from voice_flow import smart_paste

            if not smart_paste.soll_kaskadieren(
                    self.resolved_paste_mode(),
                    bool(getattr(self, "_letztes_diktat", None)),
                    smart_paste.clipboard_stand(),
                    getattr(self, "_clipboard_stand", None),
                    getattr(self, "_kaskade_aktiv", False)):
                return False
        except Exception as ex:
            log.debug("Cmd+V-Entscheidung fehlgeschlagen, native: %s", ex)
            return False
        self._kaskade_aktiv = True   # sofort, nicht erst im Thread: das naechste
        threading.Thread(target=self._cmd_v_kaskade, daemon=True).start()
        return True

    def _cmd_v_kaskade(self) -> None:
        try:
            self._warte_auf_losgelassene_tasten()
            letztes = self._letztes_diktat
            mode = self.resolved_paste_mode()
            _, bilder = self._kaskade_einfuegen(
                letztes["text"], letztes["shots"], letztes["captures"],
                letztes["duration"], mode)
            log.info("REPASTE  ✓ per Cmd+V: %d Worte + %d Bild(er)",
                     len(letztes["text"].split()), bilder)
        except Exception as ex:
            log.error("Cmd+V-Kaskade fehlgeschlagen: %s", ex)
            if self.overlay:
                self.overlay.show_info(f"Einfuegen fehlgeschlagen: {ex}", 5000)
        finally:
            self._kaskade_aktiv = False

    def on_repaste_hotkey(self) -> None:
        """Das letzte Diktat noch einmal einfuegen — Text, dann Bilder.

        19.08 Bastian: falscher Tab erwischt, oder die Bilder kamen nicht mit.
        Richtiges Feld anklicken, Kuerzel druecken, alles ist wieder da.

        Der Modus zaehlt IN DIESEM MOMENT: steht der Schalter jetzt auf AI-Web,
        bekommt der Browser Bildnummern und die Bilder selbst, auch wenn das
        Diktat urspruenglich fuer Claude Code gedacht war.
        """
        log.debug("REPASTE  Kuerzel gedrueckt.")
        letztes = getattr(self, "_letztes_diktat", None)
        if not letztes:
            log.info("REPASTE  nichts zu wiederholen — noch kein Diktat in diesem Lauf.")
            if self.overlay:
                self.overlay.show_info("Noch kein Diktat zum Wiederholen.", 3000)
            return

        # Das Kuerzel selbst haelt Umschalt/Befehl gedrueckt. Wuerde jetzt sofort
        # Befehl+V gesendet, kaeme in der Ziel-App Befehl+Umschalt+V an — in
        # Chrome "als Klartext einfuegen", also genau das Falsche.
        self._warte_auf_losgelassene_tasten()

        mode = self.resolved_paste_mode()
        try:
            _, bilder = self._kaskade_einfuegen(
                letztes["text"], letztes["shots"], letztes["captures"],
                letztes["duration"], mode)
        except Exception as ex:
            log.error("Wiederholtes Einfuegen fehlgeschlagen: %s", ex)
            if self.overlay:
                self.overlay.show_info(f"Wiederholen fehlgeschlagen: {ex}", 5000)
            return

        wortzahl = len(letztes["text"].split())
        zusatz = f" + {bilder} Bild(er)" if bilder else ""
        log.info("REPASTE  ✓ %d Worte%s (Modus %s)", wortzahl, zusatz, mode)
        if self.overlay:
            self.overlay.show_info(
                f"Nochmal eingefuegt: {wortzahl} Worte{zusatz}", 3000)

    def _warte_auf_losgelassene_tasten(self, grenze: float = 1.5) -> None:
        """Warten bis keine Zusatztaste mehr haengt (hoechstens `grenze` Sekunden)."""
        import sys as _sys

        if _sys.platform == "darwin":
            from voice_flow import _keyboard_mac as kb
        else:
            import keyboard as kb

        ende = time.monotonic() + grenze
        while time.monotonic() < ende:
            if not any(kb.is_pressed(t) for t in ("shift", "cmd", "ctrl", "alt")):
                time.sleep(0.05)   # der Ziel-App einen Wimpernschlag geben
                return
            time.sleep(0.03)
        log.debug("Zusatztasten noch gedrueckt — fuege trotzdem ein.")

    def on_annotate_hotkey(self) -> None:
        """F6: Loom-Zeichen-Overlay auf dem Monitor unter der Maus oeffnen.

        Das Overlay-QWidget wird NICHT hier (Hook-Thread) erzeugt, sondern via
        overlay.open_annotate thread-safe auf dem Qt-Thread. Der on_shoot-Callback
        laeuft ebenfalls auf dem Qt-Thread und legt das fertige PNG in den Bucket.
        """
        log.debug("F6: Handler betreten (overlay=%s)", bool(self.overlay))
        if not self.overlay:
            return
        from voice_flow.screenshot import get_cursor_pos, pick_monitor
        try:
            from mss import MSS
            with MSS() as sct:
                mon = pick_monitor(get_cursor_pos(), sct.monitors)
        except Exception as ex:
            log.error("Annotate: Monitor-Auswahl fehlgeschlagen: %s", ex)
            return
        sess = self._ensure_session()
        # Offset zum F6-Druck-Zeitpunkt festhalten: das Zeichnen dauert, der
        # Sprech-Offset gehoert aber an die Stelle wo Bastian markiert, nicht ans
        # spaetere Speichern (Aufnahme kann dann schon gestoppt sein).
        shoot_offset = self._capture_offset()

        def on_shoot(img) -> None:
            # Erst hier zaehlt die Freigabe: ohne sie waere das Bild leer.
            if not self._bildschirm_freigabe_ok():
                return
            try:
                path = sess.add_screenshot(img, offset=shoot_offset)
            except Exception as ex:
                log.error("Annotate: Screenshot speichern fehlgeschlagen: %s", ex)
                return
            if self.overlay:
                from voice_flow.notifications import ToastKind
                self.overlay.notify(
                    ToastKind.SCREENSHOT, f"Markiert {len(sess.shots)}", path.name,
                    thumbnail_path=str(path),
                    actions=[("Ordner", lambda d=sess.dir: _open_folder(d))],
                )

        log.debug("F6: open_annotate wird gerufen (monitor=%s)", mon)
        self.overlay.open_annotate(mon, on_shoot)

    # ---------- Pipeline ----------

    def _process_pipeline(self, wav: bytes, duration: float) -> None:
        success_shown = False
        backup_path = None
        try:
            if duration < self.config.min_recording_sec:
                log.info(
                    "SKIP   Aufnahme zu kurz (%.2fs < %.2fs).",
                    duration,
                    self.config.min_recording_sec,
                )
                return

            # Backup auf Disk BEVOR Whisper-Call — bei Fehler bleibt das Audio.
            # 11.07 Bastian: KEIN Size-Check mehr. Der alte Check mass die rohen
            # WAV-Bytes (14.5-Min-Diktat = 27 MB → abgebrochen), obwohl der
            # Upload als Opus nur ~2 MB gewesen waere. Lang-Audio chunkt jetzt
            # der Transcriber selbst (audio_chunks) — "zu lang" gibt es nicht mehr.
            backup_path = save_recording(wav)

            log.info("PROC   %.1fs Audio → Whisper …", duration)
            t0 = time.time()

            prompt = self._whisper_prompt()
            raw = self.transcriber.transcribe(
                wav,
                language=self.config.language,
                prompt=prompt,
            )
            t_whisper = time.time() - t0

            if not raw:
                log.warning("WHISPER  leeres Ergebnis.")
                return

            log.info("WHISPER  [%.1fs] %s", t_whisper, _truncate(raw, 200))

            cleaned = raw
            if self.cleaner.available:
                t1 = time.time()
                cleaned, meta = self.cleaner.cleanup(raw)
                t_clean = time.time() - t1
                if "error" in meta:
                    log.warning("CLEANUP  Fehler, nutze Rohtext: %s", meta["error"])
                else:
                    log.info(
                        "CLEANUP  [%.1fs in=%d out=%d] %s",
                        t_clean,
                        meta.get("input_tokens", 0),
                        meta.get("output_tokens", 0),
                        _truncate(cleaned, 200),
                    )

            # 27.06 Bastian: Screenshot-Marker proportional zur Sprechzeit einweben.
            # captures kommen aus der Session (F7/F6 waehrend der Aufnahme).
            # 18.08 Bastian: Marker-Form haengt am Ziel — Claude Code bekommt den
            # Pfad, ein Web-Chat die Bildnummer (dort ist der Pfad wertlos, weil
            # der Browser das Verzeichnis nicht hat).
            shots = list(self.session.shots) if self.session is not None else []
            caps_roh = list(self.session.captures) if self.session is not None else []

            # 19.08 Bastian: "wenn Bilder mal nicht mitgeliefert wurden oder man
            # im falschen Tab war — wieder Strg+V und dann erst Text und danach
            # die Bilder". Dafuer wird das Diktat OHNE Marker gemerkt: beim
            # Wiederholen werden die Marker im dann gueltigen Modus neu gesetzt,
            # sonst stuenden im Web-Chat Dateipfade, die dort nichts nuetzen.
            self._letztes_diktat = {
                "text": cleaned,
                "shots": shots,
                "captures": caps_roh,
                "duration": duration,
            }

            self._ensure_target_frontmost()
            mode = self.resolved_paste_mode()
            final_text, pasted_images = self._kaskade_einfuegen(
                cleaned, shots, caps_roh, duration, mode)
            total_s = time.time() - t0
            word_count = len(cleaned.split())
            log.info(
                "PASTE  ✓  total %.1fs (%d Worte)  · Clipboard%s",
                total_s, word_count,
                "=Original wiederhergestellt" if self.config.enable_clipboard_restore
                else "=transkribierter Text (Strg+V einfuegbar)",
            )

            # Persistent History — sodass Bastian spaeter alles wiederfindet
            append_transcript(
                text=final_text,
                duration_sec=duration,
                word_count=word_count,
                model=self.config.whisper_model,
                pipeline_ms=int(total_s * 1000),
            )

            # 27.06 Bastian: Transkript + F7-Screenshots zu bundle.md verschnueren.
            # Lokale Referenz greifen, damit ein paralleler F7 (neue Session) nicht
            # mitten rein grätscht; danach Session schliessen, sodass die naechste
            # Aufnahme/F7 einen frischen Bucket bekommt (Critic P2: 1 Session = 1 Zyklus).
            sess = self.session
            if sess is not None:
                try:
                    sess.set_transcript(final_text)
                    sess.build_bundle()
                except Exception as ex:
                    log.warning("Session-Bundle konnte nicht gebaut werden: %s", ex)
                with self._state_lock:
                    if self.session is sess:
                        self.session = None

            # 07.07 Bastian: Whisper wertet auch eine Halluzination als "Erfolg"
            # (Text != leer). Frueher wurde das Audio danach geloescht -> eine
            # kaputte Aufnahme (verzerrtes Bluetooth-Mikro) war unwiederbringlich
            # weg. Jetzt: verdaechtige Transkription -> Audio BEHALTEN fuer Retry.
            suspect, suspect_reason = is_suspect_transcription(cleaned, duration)
            if suspect:
                log.warning("VERDACHT  %s — Audio behalten statt loeschen.", suspect_reason)
                mark_suspect(backup_path)
                backup_path = None
                if self.overlay:
                    self.overlay.show_info(
                        f"⚠ Transkription verdaechtig · Audio behalten ({suspect_reason})",
                        duration_ms=6000,
                    )
                    success_shown = True
            else:
                # Erfolg → WAV als winziges Opus-Archiv behalten (11.07 Bastian:
                # "immer storen") statt Hard-Delete. Retention raeumt zeitgesteuert.
                archive_recording(backup_path)
                backup_path = None

            # Apple-style success-Flash an der Pille (kurz, bottom-center).
            if self.overlay and not suspect:
                word_label = f"{word_count} Wort" if word_count == 1 else f"{word_count} Woerter"
                self.overlay.show_success(
                    f"{word_label} · {total_s:.1f}s",
                    duration_ms=1100,
                )
                success_shown = True
                # Premium Toast top-right mit Kopieren-Action (die Pille kann keine Actions).
                from voice_flow.notifications import ToastKind
                image_note = (
                    f" · {pasted_images} Bild" if pasted_images == 1
                    else f" · {pasted_images} Bilder" if pasted_images else ""
                )
                self.overlay.notify(
                    ToastKind.TRANSCRIPT,
                    f"{word_label}",
                    f"{total_s:.1f}s · eingefuegt{image_note}",
                    actions=[("Kopieren", lambda t=final_text: _copy_to_clipboard(t))],
                    duration_ms=4500,
                )

        except TranscriberAuthError as ex:
            log.error("Auth-Fehler: %s", ex)
            if self.config.enable_sound:
                beep_error()
            with self._state_lock:
                if not self._auth_error_shown:
                    self._auth_error_shown = True
                    threading.Thread(
                        target=show_error,
                        args=("Voice Flow — OpenAI-Key fehlt/ungueltig", str(ex)),
                        daemon=True,
                    ).start()
        except Exception as ex:
            log.exception("PIPELINE failed: %s", ex)
            if self.config.enable_sound:
                beep_error()
        finally:
            # Bei Pipeline-Fehler: Backup mit _failed-Suffix renamen damit
            # User sieht "hier liegt eine Aufnahme die nicht durchging".
            if backup_path is not None:
                failed = mark_failed(backup_path)
                log.warning("Aufnahme gesichert fuer manuellen Retry: %s", failed)
                if self.overlay and not success_shown:
                    self.overlay.show_info(
                        "Aufnahme gesichert · siehe ~/.voice-flow/recordings/",
                        duration_ms=3000,
                    )
                    success_shown = True  # damit reset_state das overlay nicht killt
            self._reset_state(error=False, keep_overlay=success_shown)

    def _whisper_prompt(self) -> str | None:
        """Erste 220 Zeichen des ersten Context-Blocks als Whisper-Prompt.

        OpenAI empfiehlt kurze Prompts. Lange Prompts werden ignoriert/getrunkiert.
        """
        if not self.config.context:
            return None
        first_block = self.config.context.split("\n\n")[0]
        return first_block[:220]

    def _reset_state(self, error: bool = False, keep_overlay: bool = False) -> None:
        # Alle State- und UI-Updates atomic im Lock (Critic P0-1).
        # keep_overlay=True: pipeline hat schon einen self-hiding success-flash gestartet,
        # wir wuerden ihn sonst sofort wieder verstecken.
        with self._state_lock:
            self.state = self.STATE_IDLE
            self._hotkey_down = False
            if error:
                self._tray_set("error")
            else:
                self._tray_set("idle")
            if self.overlay and not keep_overlay:
                self.overlay.hide()

    def show_ready(self) -> None:
        """Signalisiert dem User: Voice Flow ist gestartet und bereit."""
        # Late import damit zirkulaere Abhaengigkeiten kein Problem werden
        from voice_flow.cli import format_hotkey_display
        hotkey_display = format_hotkey_display(self.config.hotkey)
        verb = "druecken" if self.config.hotkey_mode == "toggle" else "halten"
        msg = f"Voice Flow bereit · {hotkey_display} {verb}"
        log.info(msg.replace(" · ", "  ·  "))
        if self.overlay:
            self.overlay.show_info(msg, duration_ms=3000)
        if self.config.enable_sound:
            beep_ready()
        self.offer_pending_recovery()

    def offer_pending_recovery(self) -> None:
        """Liegengebliebene Aufnahmen sichtbar und per Klick einloesbar machen.

        Vorher stand nur eine Log-Zeile mit einem Terminal-Befehl im Logfile —
        fuer Bastian (kein Entwickler) faktisch unerreichbar: das Audio war
        gerettet, aber er kam nicht dran. Bewusst KEINE Auto-Transkription:
        jede Datei kostet einen API-Call, das entscheidet der User per Klick.
        """
        if not self.overlay:
            return
        try:
            pending = list_pending_with_audio()
        except Exception as ex:  # noqa: BLE001 - Hinweis darf den Start nie kippen
            log.debug("Pending-Pruefung fehlgeschlagen: %s", ex)
            return
        if not pending:
            return

        from voice_flow.notifications import ToastKind

        minutes = sum(_wav_minutes(p) for p in pending)
        self.overlay.notify(
            ToastKind.ERROR,
            f"{len(pending)} Aufnahme(n) ohne Text",
            # Kurz halten: der Toast kuerzt laengere Zeilen mit "…" ab (selbst
            # gesehen im Screenshot 16.08. — "transkribierb…").
            f"~{minutes:.0f} Min Audio gesichert",
            actions=[("Jetzt nachholen", lambda: self._recover_pending_async(pending))],
            duration_ms=15000,
        )

    def _recover_pending_async(self, paths: list) -> None:
        """Nachtranskription im Hintergrund — der Klick darf die UI nicht blockieren."""

        def _run() -> None:
            from voice_flow.recover import recover_file

            done, failed, last = 0, 0, ""
            for path in paths:
                if not path.exists():  # zwischenzeitlich schon erledigt
                    continue
                try:
                    text = recover_file(path, self.transcriber, self.config)
                except Exception as ex:  # noqa: BLE001 - eine kaputte Datei stoppt den Rest nicht
                    log.error("Nachholen fehlgeschlagen (%s): %s", path.name, ex)
                    failed += 1
                    continue
                if text:
                    done += 1
                    last = text
            if last:
                # Bewusst NUR ins Clipboard (kein paste_to_active_window): der User
                # klickt den Toast irgendwo, ein automatisches Cmd+V wuerde den Text
                # in ein zufaelliges Fenster schiessen.
                try:
                    import pyperclip

                    pyperclip.copy(last)
                except Exception as ex:  # noqa: BLE001 - Clipboard ist Komfort
                    log.debug("Clipboard nach Recovery nicht beschreibbar: %s", ex)
            if not self.overlay:
                return
            from voice_flow.notifications import ToastKind

            if done:
                self.overlay.notify(
                    ToastKind.SUCCESS,
                    f"{done} Aufnahme(n) nachgeholt",
                    "Letzter Text liegt in der Zwischenablage (Cmd+V)"
                    + (f" · {failed} fehlgeschlagen" if failed else ""),
                    duration_ms=12000,
                )
            else:
                self.overlay.notify(
                    ToastKind.ERROR,
                    "Nachholen ergab keinen Text",
                    "Aufnahmen bleiben gespeichert — vermutlich Stille.",
                    duration_ms=10000,
                )

        threading.Thread(target=_run, daemon=True, name="voice-flow-recover").start()

    def shutdown(self) -> None:
        """Sauberes Shutdown: laufendes Recording stoppen, Audio unmuten, UI schliessen."""
        log.info("Voice Flow shutdown initiated.")
        try:
            if self.state == self.STATE_RECORDING:
                self.recorder.stop()
        except Exception as ex:
            log.debug("Recorder cleanup error (egal): %s", ex)
        # Wichtig: Audio unmuten bevor Process endet, sonst bleibt System gemuted
        if self.audio_mute:
            try:
                self.audio_mute.unmute()
            except Exception as ex:
                log.debug("Audio-unmute cleanup error: %s", ex)
        if self.overlay:
            try:
                self.overlay.stop()
            except Exception as ex:
                log.debug("Overlay cleanup error: %s", ex)

    def _tray_set(self, state: str) -> None:
        # Status-Punkt im Control-Fenster (Taskleiste) mitziehen — unabhaengig vom Tray.
        if self.overlay:
            self.overlay.set_app_state(state)
        if not self.tray:
            return
        try:
            getattr(self.tray, f"set_{state}")()
        except Exception as ex:
            log.debug("Tray-Update auf %s fehlgeschlagen: %s", state, ex)


def _truncate(s: str, n: int) -> str:
    s = s.replace("\n", " ").strip()
    return s if len(s) <= n else s[:n] + "…"


def _wav_minutes(path) -> float:
    """Laenge einer WAV in Minuten — nur fuer die Anzeige im Hinweis.

    Liest den Header statt der Datei (Backups sind bis zu dreistellige MB).
    Unlesbar → 0.0, der Hinweis nennt dann eben eine kleinere Zahl.
    """
    import wave

    try:
        with wave.open(str(path), "rb") as wf:
            rate = wf.getframerate()
            return wf.getnframes() / rate / 60.0 if rate else 0.0
    except Exception:  # noqa: BLE001 - Anzeige-Detail, nie ein Startfehler
        return 0.0


def _copy_to_clipboard(text: str) -> None:
    """Toast-Action 'Kopieren' — Transkript erneut ins Clipboard legen."""
    import pyperclip
    try:
        pyperclip.copy(text)
    except Exception as ex:
        log.warning("Kopieren ins Clipboard fehlgeschlagen: %s", ex)


def _open_folder(path) -> None:
    """Toast-Action 'Ordner' — den Session-Bucket im Dateimanager oeffnen."""
    import os
    import sys
    try:
        if sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", str(path)])
        else:
            os.startfile(str(path))  # Windows
    except Exception as ex:
        log.warning("Ordner oeffnen fehlgeschlagen: %s", ex)
