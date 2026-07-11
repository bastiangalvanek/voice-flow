"""Eine liegengebliebene Aufnahme mit ihrem Screenshot-Bucket zusammenführen.

Warum (11.07 Bastian "die Bilder fehlen im Transkript"): Im Live-Betrieb webt
die Pipeline die F7/F6-Screenshots proportional zur Sprechzeit ins Transkript
(app._process_pipeline → weave_screenshot_markers). Scheitert die Aufnahme
aber vorher (25-MB-Fail, Crash), bleibt der Session-Bucket verwaist — die
Offsets (Sekunde-seit-Start je Shot) leben nur im RAM der Session-Instanz und
werden nie persistiert.

Rekonstruktion beim Recovern: Der Session-Ordner heißt nach seinem START
(`YYYY-MM-DD_HH-MM-SS`), die WAV nach ihrem STOP (`recording_YYYYMMDD_HHMMSS`).
Über Start = Stop − Dauer lässt sich der Bucket eindeutig zuordnen, und der
Offset jedes Screenshots = Datei-mtime − Session-Start. Nicht sample-genau wie
der Live-Pfad, aber die zeitliche Reihenfolge und grobe Position stimmen — genau
das, was die proportionale Platzierung braucht.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

_SESSION_DIR_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})$")
_RECORDING_TS_RE = re.compile(r"recording_(\d{8})_(\d{6})")
# Session-Start und (Recording-Stop − Dauer) dürfen so weit auseinanderliegen
# und der Bucket zählt noch als Treffer (deckt Rundung + Verarbeitungs-Latenz).
MATCH_TOLERANCE_SEC = 180.0


def parse_session_start(session_dir: Path) -> datetime | None:
    """`2026-07-11_16-55-16` → datetime. None bei fremdem Ordnernamen."""
    m = _SESSION_DIR_RE.match(session_dir.name)
    if not m:
        return None
    try:
        return datetime.strptime(session_dir.name, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None


def parse_recording_stop(recording_path: Path) -> datetime | None:
    """`recording_20260711_170948_502...` → Stop-datetime (Sekunde). None sonst."""
    m = _RECORDING_TS_RE.search(recording_path.name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def find_session_for(
    recording_path: Path, duration: float, sessions_dir: Path
) -> Path | None:
    """Den Screenshot-Bucket zu einer Aufnahme finden (über Start=Stop−Dauer).

    Nimmt den Bucket mit dem geringsten Start-Abstand innerhalb der Toleranz,
    der auch mindestens einen Screenshot enthält. None wenn keiner passt.
    """
    stop = parse_recording_stop(recording_path)
    if stop is None or not sessions_dir.exists():
        return None
    expected_start = stop.timestamp() - duration

    best: tuple[float, Path] | None = None
    for d in sessions_dir.iterdir():
        if not d.is_dir():
            continue
        start = parse_session_start(d)
        if start is None:
            continue
        if not any(d.glob("shot_*.png")):
            continue
        delta = abs(start.timestamp() - expected_start)
        if delta <= MATCH_TOLERANCE_SEC and (best is None or delta < best[0]):
            best = (delta, d)
    return best[1] if best else None


def derive_captures(session_dir: Path, marker_fmt: str) -> list[tuple[float, str]]:
    """(offset_sekunden, marker) je Screenshot, Offset aus mtime − Session-Start.

    marker_fmt bekommt {n} (1-basiert), {name} und {path} (absolut). Screenshots
    mit mtime VOR dem Start (Uhr-Schräglage) werden auf 0 geklemmt. Sortiert nach
    Offset — die Reihenfolge im Bucket (shot_01..NN) ist ohnehin chronologisch.
    """
    start = parse_session_start(session_dir)
    if start is None:
        return []
    start_ts = start.timestamp()
    shots = sorted(session_dir.glob("shot_*.png"))
    captures: list[tuple[float, str]] = []
    for i, shot in enumerate(shots, start=1):
        offset = max(0.0, shot.stat().st_mtime - start_ts)
        marker = marker_fmt.format(n=i, name=shot.name, path=str(shot.resolve()))
        captures.append((offset, marker))
    return captures
