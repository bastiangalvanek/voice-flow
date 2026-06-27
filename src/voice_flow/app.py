from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from voice_flow.audio import AudioRecorder
from voice_flow.audio_mute import SystemAudioMute
from voice_flow.cleanup import Cleaner
from voice_flow.config import Config
from voice_flow.gui_errors import show_error
from voice_flow.overlay import RecordingOverlay
from voice_flow.paste import paste_to_active_window
from voice_flow.recording_storage import (
    check_size_for_whisper,
    delete_recording,
    mark_failed,
    save_recording,
)
from voice_flow.sound import beep_error, beep_ready, beep_start, beep_stop
from voice_flow.transcript_history import append_transcript
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
        self.recorder = AudioRecorder(
            sample_rate=config.sample_rate,
            channels=config.channels,
            device=config.audio_device,
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
            if self.overlay:
                self.overlay.show_recording()

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
            with self._state_lock:
                self.state = self.STATE_IDLE
                self._hotkey_down = False
                self._tray_set("error")
                if self.overlay:
                    self.overlay.hide()

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

    def on_screenshot_hotkey(self) -> None:
        """F7: Monitor unter der Maus grabben, in den Session-Bucket legen, Toast zeigen."""
        from voice_flow.screenshot import grab_monitor_under_cursor
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

    def on_annotate_hotkey(self) -> None:
        """F6: Loom-Zeichen-Overlay auf dem Monitor unter der Maus oeffnen.

        Das Overlay-QWidget wird NICHT hier (Hook-Thread) erzeugt, sondern via
        overlay.open_annotate thread-safe auf dem Qt-Thread. Der on_shoot-Callback
        laeuft ebenfalls auf dem Qt-Thread und legt das fertige PNG in den Bucket.
        """
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

            # Backup auf Disk BEVOR Whisper-Call — bei Fehler bleibt das Audio
            backup_path = save_recording(wav)

            # Size-Check fuer Whisper-25-MB-Limit
            ok, msg = check_size_for_whisper(wav)
            if msg:
                log.warning("AUDIO  %s", msg)
            if not ok:
                # Datei bleibt gesichert, aber wir versuchen den Call gar nicht erst
                mark_failed(backup_path)
                backup_path = None  # nicht nochmal anfassen im finally
                if self.overlay:
                    self.overlay.show_info(
                        f"Aufnahme zu lang ({len(wav) // 1024 // 1024} MB) · gesichert",
                        duration_ms=2800,
                    )
                return

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
            final_text = cleaned
            caps = []
            if self.session is not None:
                from pathlib import Path
                for off, p in self.session.captures:
                    caps.append((off, f"(siehe {Path(p).name} im Bucket: {p})"))
            if caps:
                final_text = weave_screenshot_markers(cleaned, caps, duration)

            paste_to_active_window(
                final_text,
                restore_clipboard=self.config.enable_clipboard_restore,
            )
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

            # Erfolg → Backup loeschen, brauchen wir nicht mehr
            delete_recording(backup_path)
            backup_path = None

            # Apple-style success-Flash an der Pille (kurz, bottom-center).
            if self.overlay:
                word_label = f"{word_count} Wort" if word_count == 1 else f"{word_count} Woerter"
                self.overlay.show_success(
                    f"{word_label} · {total_s:.1f}s",
                    duration_ms=1100,
                )
                success_shown = True
                # Premium Toast top-right mit Kopieren-Action (die Pille kann keine Actions).
                from voice_flow.notifications import ToastKind
                self.overlay.notify(
                    ToastKind.TRANSCRIPT,
                    f"{word_label}",
                    f"{total_s:.1f}s · eingefuegt",
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

    def _whisper_prompt(self) -> Optional[str]:
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


def _copy_to_clipboard(text: str) -> None:
    """Toast-Action 'Kopieren' — Transkript erneut ins Clipboard legen."""
    import pyperclip
    try:
        pyperclip.copy(text)
    except Exception as ex:
        log.warning("Kopieren ins Clipboard fehlgeschlagen: %s", ex)


def _open_folder(path) -> None:
    """Toast-Action 'Ordner' — den Session-Bucket im Explorer oeffnen."""
    import os
    try:
        os.startfile(str(path))
    except Exception as ex:
        log.warning("Ordner oeffnen fehlgeschlagen: %s", ex)
