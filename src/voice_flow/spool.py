"""Live-Spool: die laufende Aufnahme steht schon WAEHREND des Sprechens auf Platte.

Warum (Vorfall 16.08.2026): `save_recording()` laeuft erst NACH `recorder.stop()`.
Als CoreAudio beim Mikro-Wechsel im Stop deadlockte, lagen 2m54s Diktat
ausschliesslich im RAM des eingefrorenen Prozesses und mussten per lldb-Injektion
gerettet werden. Ein `kill -9` haette sie endgueltig vernichtet.

Der Spool schliesst diese Luecke: ein Hintergrund-Thread haengt die bereits
aufgenommenen Frames alle paar Sekunden an eine `_partial.wav` an. Der
Audio-Callback selbst bleibt I/O-frei (Realtime-Pfad!) — er fuellt nur die Liste,
der Spool-Thread liest sie ab seinem Index nach.

Der WAV-Header wird nach JEDEM Flush auf die aktuelle Laenge gepatcht. Damit ist
die Datei zu jedem Zeitpunkt eine gueltige WAV — auch nach Absturz, Stromausfall
oder `kill -9`. Genau das kann das stdlib-`wave`-Modul nicht (es schreibt die
Groessen erst beim `close()`).

Ueberlebende `_partial.wav` gelten als offene Arbeit: die Retention fasst sie nie
an, `list_pending_recordings()` meldet sie beim Start, `python -m voice_flow.recover`
transkribiert sie nach.
"""
from __future__ import annotations

import logging
import struct
import threading
from pathlib import Path

log = logging.getLogger(__name__)

# Flush-Intervall = das Maximum, das ein harter Absturz kosten kann. Gemessen
# 16.08.2026 (echtes Mikro + kill -9): bei 3s gingen 2s verloren, bei 1s nur der
# angefangene Block. 16 kHz mono int16 = 32 KB/s — dieses I/O ist geschenkt.
FLUSH_INTERVAL_SEC = 1.0

_RIFF_SIZE_OFFSET = 4  # RIFF-Chunk-Groesse (= 36 + data-Bytes)
_DATA_SIZE_OFFSET = 40  # data-Chunk-Groesse
_HEADER_BYTES = 44


def build_wav_header(sample_rate: int, channels: int, sampwidth: int, data_bytes: int) -> bytes:
    """Kanonischer 44-Byte-PCM-WAV-Header fuer eine bekannte Datenlaenge."""
    byte_rate = sample_rate * channels * sampwidth
    block_align = channels * sampwidth
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_bytes,
        b"WAVE",
        b"fmt ",
        16,
        1,  # PCM
        channels,
        sample_rate,
        byte_rate,
        block_align,
        sampwidth * 8,
        b"data",
        data_bytes,
    )


class WavSpool:
    """Append-Writer, dessen Datei nach jedem Flush eine gueltige WAV ist."""

    def __init__(
        self,
        path: Path,
        sample_rate: int = 16000,
        channels: int = 1,
        sampwidth: int = 2,
    ):
        self.path = Path(path)
        self.sample_rate = sample_rate
        self.channels = channels
        self.sampwidth = sampwidth
        self._fh = None
        self._data_bytes = 0
        self._lock = threading.Lock()

    @property
    def data_bytes(self) -> int:
        return self._data_bytes

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("wb")
        self._fh.write(build_wav_header(self.sample_rate, self.channels, self.sampwidth, 0))
        self._fh.flush()
        self._data_bytes = 0

    def write(self, chunk: bytes) -> None:
        """Haengt PCM-Bytes an und patcht die Groessen im Header."""
        if not chunk:
            return
        with self._lock:
            # Der None-Check MUSS im Lock stehen: sonst kann close() die Datei
            # zwischen Pruefung und seek() schliessen (letzter Flush trifft
            # dann auf None und wirft).
            if self._fh is None:
                return
            self._fh.seek(_HEADER_BYTES + self._data_bytes)
            self._fh.write(chunk)
            self._data_bytes += len(chunk)
            # Header auf die neue Laenge patchen -> Datei ist JETZT gueltig,
            # nicht erst beim close(). Das ist der ganze Trick.
            self._fh.seek(_RIFF_SIZE_OFFSET)
            self._fh.write(struct.pack("<I", 36 + self._data_bytes))
            self._fh.seek(_DATA_SIZE_OFFSET)
            self._fh.write(struct.pack("<I", self._data_bytes))
            self._fh.flush()

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                try:
                    self._fh.close()
                finally:
                    self._fh = None

    def discard(self) -> None:
        """Erfolgsfall: die vollstaendige WAV kam aus dem RAM, Spool wird ueberfluessig."""
        self.close()
        try:
            self.path.unlink(missing_ok=True)
        except Exception as ex:  # noqa: BLE001 - Aufraeumen darf nie den Stop kippen
            log.debug("Spool-Datei nicht loeschbar (%s): %s", self.path, ex)
