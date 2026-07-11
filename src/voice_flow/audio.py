from __future__ import annotations

import io
import logging
import re
import threading
import wave
from collections.abc import Callable

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)

def clean_device_name(raw: str) -> str:
    """Menschenlesbarer Mikro-Name fuer das Dropdown.

    WDM-KS liefert rohe Pin-Namen wie
    'Kopfhörer (@System32\\drivers\\bthhfenum.sys,#2;%1 Hands-Free%0\\r\\n;(Poly
    VFOCUS2 Series))' — mit Treiberpfad UND Zeilenumbruch. Wir kollabieren
    Whitespace und ziehen bei solchen Bluetooth-Pins den echten Geraetenamen
    (letzter Klammer-Block) heraus.
    """
    name = " ".join(str(raw).split())  # kollabiert auch \r\n
    if "bthhfenum" in name or "@System32" in name:
        inner = re.findall(r"\(([^()]+)\)", name)
        if inner:
            return f"{inner[-1].strip()} (Bluetooth)"
    return name


def list_input_devices() -> list[tuple[int, str]]:
    """Alle vorhandenen Mikrofone als (Index, Name) — fuer das UI-Dropdown.

    Dedupliziert nach Name (Windows listet dasselbe Geraet oft ueber mehrere
    Host-APIs). Erster Treffer je Name gewinnt.
    """
    seen: set[str] = set()
    out: list[tuple[int, str]] = []
    for index, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) < 1:
            continue
        name = str(dev.get("name", "")).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append((index, name))
    return out


def _norm(s: str) -> str:
    """Whitespace kollabieren + lowercase — robust gegen \\r\\n in WDM-KS-Namen."""
    return " ".join(str(s).split()).lower()


def _find_input_by_name(devices: list[dict], want: str) -> int | None:
    """Erstes Eingabegeraet, dessen Name den Substring enthaelt (case-insensitive,
    whitespace-normalisiert)."""
    needle = _norm(want)
    if not needle:
        return None
    for index, dev in enumerate(devices):
        if dev.get("max_input_channels", 0) < 1:
            continue
        if needle in _norm(dev.get("name", "")):
            return index
    return None


def _first_input_device(devices: list[dict]) -> int | None:
    """Erstes verfuegbares Eingabegeraet (Notnagel), sonst None."""
    for index, dev in enumerate(devices):
        if dev.get("max_input_channels", 0) >= 1:
            return index
    return None


def resolve_input_device(configured: int | str | None, sample_rate: int) -> int:
    """Ermittelt einen NUTZBAREN Eingabegeraet-Index. Simpel, drei Stufen:

    1. Was du sagst: VOICE_FLOW_AUDIO_DEVICE = Index (7) ODER Name-Teil ("Poly").
       Name-Match ist robust gegen wechselnde Geraete-Indizes.
    2. Sonst der Windows-Standard, SOFERN gesetzt (>= 0).
    3. Sonst das erste vorhandene Mikro — sonst waere F8 tot. Genau hier lag der
       "Fehler": Windows hatte KEINEN Standard-Input (Index -1), und
       `sd.InputStream(device=None)` crasht dann mit "Error querying device -1".

    Raises RuntimeError, wenn wirklich kein Eingabegeraet existiert.
    """
    if isinstance(configured, int) and configured >= 0:
        return configured
    if isinstance(configured, str) and configured.strip():
        hit = _find_input_by_name(list(sd.query_devices()), configured)
        if hit is not None:
            return hit
        log.warning(
            "Mikro %r nicht gefunden — nutze Windows-Standard bzw. erstes Mikro.",
            configured,
        )

    default_input = sd.default.device[0]
    if isinstance(default_input, int) and default_input >= 0:
        return default_input

    picked = _first_input_device(list(sd.query_devices()))
    if picked is None:
        raise RuntimeError(
            "Kein Mikrofon gefunden. Schliesse ein Mikrofon an oder waehle in den "
            "Windows-Sound-Einstellungen ein Standard-Eingabegeraet."
        )
    log.warning(
        "Kein Windows-Standard-Mikro gesetzt (Index -1) — Voice Flow nutzt "
        "das erste vorhandene Mikro [%s].", picked,
    )
    return picked


class AudioRecorder:
    """Push-to-Talk Recorder. Thread-safe start/stop, gibt WAV-Bytes zurueck."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        device: int | str | None | Callable[[], int | str | None] = None,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        # device kann statisch (Index/Name) ODER ein Callable sein. Callable wird
        # bei JEDEM start() ausgewertet → die UI-Mikrofon-Auswahl wirkt live,
        # ohne Neustart.
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
            # Geraet bei JEDEM Start neu aufloesen — so wirkt UI-Auswahl/Umstecken/
            # Default-Wechsel sofort, ohne Neustart. Fixt den F8-"Fehler" (device -1).
            configured = self.device() if callable(self.device) else self.device
            device = resolve_input_device(configured, self.sample_rate)
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                device=device,
                callback=self._callback,
            )
            self._stream.start()
            # 07.07 Bastian: welches Mikro + welche Rate wirklich? Ein Bluetooth-
            # Headset (Hands-Free, 8 kHz) liefert verwaschenes Audio -> Whisper
            # halluziniert / erkennt falsche Sprache. Das im Log sichtbar machen,
            # damit die Ursache beim naechsten Mal sofort erkennbar ist.
            try:
                idx = device
                dev = sd.query_devices(idx)
                name = dev["name"]
                is_bluetooth = any(t in name for t in ("Hands-Free", "bthhfenum")) \
                    or dev.get("default_samplerate", 0) < 16000
                if is_bluetooth:
                    log.warning(
                        "MIC  [%s] %s — Bluetooth/Low-Rate-Mikro! Spracherkennung "
                        "wird matschig (falsche Sprache moeglich). Echtes 16-kHz-Mikro nutzen.",
                        idx, name,
                    )
                else:
                    log.info("MIC  [%s] %s", idx, name)
            except Exception as ex:
                log.debug("Mikro-Info nicht ermittelbar: %s", ex)
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
