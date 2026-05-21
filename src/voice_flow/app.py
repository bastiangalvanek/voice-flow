from __future__ import annotations

import logging
import threading
import time

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
from voice_flow.transcription import Transcriber, TranscriberAuthError

log = logging.getLogger(__name__)


class VoiceFlowApp:
    """Controller: orchestrates Hotkey → Audio → Whisper → Cleanup → Paste.

    State machine: idle → recording → processing → idle.
    Locks prevent race conditions when hotkey events overlap.
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
        self.tray = None  # set by CLI after construction
        # Auth-error flag under lock — prevents race on rapid double-F8.
        self._auth_error_shown = False
        # Own hotkey-down tracker, independent of state, so Windows typematic
        # repeats don't fire new press events.
        self._hotkey_down = False

        # Floating overlay (Wispr-style) — runs in its own Qt thread
        self.overlay: RecordingOverlay | None = None
        if config.enable_overlay:
            try:
                # Late import so cli.format_hotkey_display is available without circular issues.
                from voice_flow.cli import format_hotkey_display
                self.overlay = RecordingOverlay(
                    always_visible=config.overlay_always_visible,
                    hotkey_display=format_hotkey_display(config.hotkey),
                )
                if not self.overlay.available:
                    self.overlay = None
                    log.warning("Overlay unavailable, running without floating UI.")
                else:
                    self.overlay.set_level_provider(lambda: self.recorder.current_level)
            except Exception as ex:
                log.warning("Overlay init failed: %s", ex)
                self.overlay = None

        # System audio mute (Wispr-style: music/meetings muted during dictation)
        self.audio_mute: SystemAudioMute | None = None
        if config.enable_audio_mute:
            try:
                self.audio_mute = SystemAudioMute()
                if not self.audio_mute.available:
                    self.audio_mute = None
                    log.info("Audio mute unavailable (pycaw missing or no default output).")
                else:
                    log.info("Audio mute active — system audio will be muted during recording.")
            except Exception as ex:
                log.warning("Audio mute init failed: %s", ex)
                self.audio_mute = None

    # ---------- Hotkey callbacks ----------

    def on_hotkey_press(self) -> None:
        # Hotkey-down filter against Windows typematic repeats (every ~50ms).
        with self._state_lock:
            if self._hotkey_down or self.state != self.STATE_IDLE:
                return
            self._hotkey_down = True
            self.state = self.STATE_RECORDING
            self._tray_set("recording")
            if self.overlay:
                self.overlay.show_recording()

        # Mute system audio BEFORE the beep, otherwise background music bleeds
        # into the microphone recording.
        if self.audio_mute:
            self.audio_mute.mute()
        if self.config.enable_sound:
            beep_start()

        try:
            self.recorder.start()
            log.info("REC ▶  hotkey=%s", self.config.hotkey.upper())
        except Exception as ex:
            log.error("Recording start failed: %s", ex)
            # Audio MUST be unmuted or system stays silent.
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
            # Always reset the hotkey-down flag, regardless of state.
            self._hotkey_down = False
            if self.state != self.STATE_RECORDING:
                return
            self.state = self.STATE_PROCESSING
            self._tray_set("processing")
            if self.overlay:
                self.overlay.show_processing()

        if self.config.enable_sound:
            beep_stop()
        if self.audio_mute:
            self.audio_mute.unmute()

        try:
            wav = self.recorder.stop()
            duration = self.recorder.duration_seconds
        except Exception as ex:
            log.error("Recording stop failed: %s", ex)
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

    # ---------- Pipeline ----------

    def _process_pipeline(self, wav: bytes, duration: float) -> None:
        success_shown = False
        backup_path = None
        try:
            if duration < self.config.min_recording_sec:
                log.info(
                    "SKIP   recording too short (%.2fs < %.2fs).",
                    duration,
                    self.config.min_recording_sec,
                )
                return

            # Backup to disk BEFORE Whisper call — on failure the audio survives.
            backup_path = save_recording(wav)

            ok, msg = check_size_for_whisper(wav)
            if msg:
                log.warning("AUDIO  %s", msg)
            if not ok:
                mark_failed(backup_path)
                backup_path = None
                if self.overlay:
                    self.overlay.show_info(
                        f"Recording too long ({len(wav) // 1024 // 1024} MB) · saved",
                        duration_ms=2800,
                    )
                return

            log.info("PROC   %.1fs audio → Whisper …", duration)
            t0 = time.time()

            prompt = self._whisper_prompt()
            raw = self.transcriber.transcribe(
                wav,
                language=self.config.language,
                prompt=prompt,
            )
            t_whisper = time.time() - t0

            if not raw:
                log.warning("WHISPER  empty result.")
                return

            log.info("WHISPER  [%.1fs] %s", t_whisper, _truncate(raw, 200))

            cleaned = raw
            if self.cleaner.available:
                t1 = time.time()
                cleaned, meta = self.cleaner.cleanup(raw)
                t_clean = time.time() - t1
                if "error" in meta:
                    log.warning("CLEANUP  error, using raw text: %s", meta["error"])
                else:
                    log.info(
                        "CLEANUP  [%.1fs in=%d out=%d] %s",
                        t_clean,
                        meta.get("input_tokens", 0),
                        meta.get("output_tokens", 0),
                        _truncate(cleaned, 200),
                    )

            paste_to_active_window(
                cleaned,
                restore_clipboard=self.config.enable_clipboard_restore,
            )
            total_s = time.time() - t0
            word_count = len(cleaned.split())
            log.info(
                "PASTE  ✓  total %.1fs (%d words)  · clipboard%s",
                total_s, word_count,
                "=original restored" if self.config.enable_clipboard_restore
                else "=transcribed text (Ctrl+V to re-paste)",
            )

            append_transcript(
                text=cleaned,
                duration_sec=duration,
                word_count=word_count,
                model=self.config.whisper_model,
                pipeline_ms=int(total_s * 1000),
            )

            delete_recording(backup_path)
            backup_path = None

            if self.overlay:
                word_label = f"{word_count} word" if word_count == 1 else f"{word_count} words"
                self.overlay.show_success(
                    f"{word_label} · {total_s:.1f}s",
                    duration_ms=1100,
                )
                success_shown = True

        except TranscriberAuthError as ex:
            log.error("Auth error: %s", ex)
            if self.config.enable_sound:
                beep_error()
            with self._state_lock:
                if not self._auth_error_shown:
                    self._auth_error_shown = True
                    threading.Thread(
                        target=show_error,
                        args=("Voice Flow — OpenAI key missing/invalid", str(ex)),
                        daemon=True,
                    ).start()
        except Exception as ex:
            log.exception("PIPELINE failed: %s", ex)
            if self.config.enable_sound:
                beep_error()
        finally:
            # On pipeline failure: rename backup with _failed suffix so the user
            # sees "here's a recording that didn't go through".
            if backup_path is not None:
                failed = mark_failed(backup_path)
                log.warning("Recording saved for manual retry: %s", failed)
                if self.overlay and not success_shown:
                    self.overlay.show_info(
                        "Recording saved · see ~/.voice-flow/recordings/",
                        duration_ms=3000,
                    )
                    success_shown = True
            self._reset_state(error=False, keep_overlay=success_shown)

    def _whisper_prompt(self) -> str | None:
        """First 220 chars of the first context block as Whisper prompt.

        OpenAI recommends short prompts. Long ones get ignored/truncated.
        """
        if not self.config.context:
            return None
        first_block = self.config.context.split("\n\n")[0]
        return first_block[:220]

    def _reset_state(self, error: bool = False, keep_overlay: bool = False) -> None:
        # All state + UI updates atomic under lock.
        # keep_overlay=True: pipeline already started a self-hiding success flash,
        # we'd otherwise hide it immediately.
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
        """Signal to the user: Voice Flow is started and ready."""
        from voice_flow.cli import format_hotkey_display
        hotkey_display = format_hotkey_display(self.config.hotkey)
        msg = f"Voice Flow ready · hold {hotkey_display}"
        log.info(msg.replace(" · ", "  ·  "))
        if self.overlay:
            self.overlay.show_info(msg, duration_ms=3000)
        if self.config.enable_sound:
            beep_ready()

    def shutdown(self) -> None:
        """Clean shutdown: stop running recording, unmute audio, close UI."""
        log.info("Voice Flow shutdown initiated.")
        try:
            if self.state == self.STATE_RECORDING:
                self.recorder.stop()
        except Exception as ex:
            log.debug("Recorder cleanup error (ignored): %s", ex)
        # Important: unmute before process ends, else system stays silent.
        if self.audio_mute:
            try:
                self.audio_mute.unmute()
            except Exception as ex:
                log.debug("Audio unmute cleanup error: %s", ex)
        if self.overlay:
            try:
                self.overlay.stop()
            except Exception as ex:
                log.debug("Overlay cleanup error: %s", ex)

    def _tray_set(self, state: str) -> None:
        if not self.tray:
            return
        try:
            getattr(self.tray, f"set_{state}")()
        except Exception as ex:
            log.debug("Tray update to %s failed: %s", state, ex)


def _truncate(s: str, n: int) -> str:
    s = s.replace("\n", " ").strip()
    return s if len(s) <= n else s[:n] + "…"
