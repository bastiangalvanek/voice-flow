from __future__ import annotations

import io
import logging
import threading
import wave

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)


class AudioRecorder:
    """Push-to-Talk Recorder. Thread-safe start/stop, gibt WAV-Bytes zurueck."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        device: int | None = None,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.device = device
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        # Live RMS-Level (0.0 .. 1.0), aktualisiert im Audio-Callback.
        # Lesbar von anderem Thread (Overlay) — float-Zuweisung ist atomic in CPython.
        self._current_level: float = 0.0
        # Duration des letzten beendeten Recordings (in Sekunden, gesetzt von stop()).
        self._frames_duration: float = 0.0

    def start(self) -> None:
        with self._lock:
            if self._stream is not None:
                raise RuntimeError("AudioRecorder.start() called while already recording.")
            self._frames = []
            self._current_level = 0.0
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                device=self.device,
                callback=self._callback,
            )
            self._stream.start()
            log.debug("Recording started (sr=%d, ch=%d).", self.sample_rate, self.channels)

    def stop(self) -> bytes:
        with self._lock:
            if self._stream is None:
                raise RuntimeError("AudioRecorder.stop() called without start().")
            try:
                # stream.close() blockt bis Callback nicht mehr feuert (PortAudio-Garantie).
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None
            # Snapshot der Frames INNERHALB des Locks, damit ein paralleler start()
            # nicht die Liste leeren kann waehrend wir sie noch lesen (Critic P0-4).
            frames_snapshot = self._frames
            self._frames = []
            self._frames_duration = (
                sum(len(f) for f in frames_snapshot) / self.sample_rate
                if frames_snapshot
                else 0.0
            )
            log.debug("Recording stopped, %d frames captured.", len(frames_snapshot))
        return self._frames_to_wav_bytes(frames_snapshot)

    @property
    def duration_seconds(self) -> float:
        """Dauer des LETZTEN beendeten Recordings, gesetzt in stop()."""
        return self._frames_duration

    @property
    def current_level(self) -> float:
        """Aktueller normalisierter RMS-Level (0.0 .. 1.0), thread-safe lesbar."""
        return self._current_level

    def _callback(self, indata, frames, time_info, status):
        if status:
            log.warning("Audio callback status: %s", status)
        self._frames.append(indata.copy())
        # RMS auf normalized float32, dann *4 fuer sichtbare Skala (Sprache ~0.1 RMS).
        # Smoothing (0.6 alt + 0.4 neu) gegen zappelnde Pegel-Anzeige.
        samples = indata.astype(np.float32, copy=False)
        rms = float(np.sqrt(np.mean(samples * samples))) / 32768.0
        target = min(1.0, rms * 4.0)
        self._current_level = 0.6 * self._current_level + 0.4 * target

    def _frames_to_wav_bytes(self, frames: list[np.ndarray]) -> bytes:
        if not frames:
            return b""
        audio = np.concatenate(frames, axis=0)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # int16
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio.tobytes())
        return buf.getvalue()
