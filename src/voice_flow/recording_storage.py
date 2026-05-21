"""Recording backup: WAV files are saved to disk before Whisper transcribes them.
On API error / crash / disconnect, the audio is preserved.

Location: ~/.voice-flow/recordings/recording_<timestamp>.wav

Lifecycle:
  1. Pipeline calls `save_recording(wav_bytes)` → returns Path
  2. Transcription runs (Whisper)
  3. Success → `delete_recording(path)` cleans up
  4. Failure → file remains, log warning with path

Auto cleanup on Voice Flow start:
  - recordings older than RETENTION_DAYS are deleted
  - prevents disk from filling up indefinitely

Known limit:
  - OpenAI Whisper API: 25 MB max per request
  - 8 min × 16 kHz mono int16 ≈ 15 MB → fits easily
  - 14 min × 16 kHz mono int16 ≈ 27 MB → exceeds (raises warning)
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

RECORDINGS_DIR = Path.home() / ".voice-flow" / "recordings"
RETENTION_DAYS = 7
WHISPER_MAX_BYTES = 25 * 1024 * 1024
WHISPER_WARN_BYTES = 22 * 1024 * 1024


def save_recording(wav_bytes: bytes, suffix: str = "") -> Path:
    """Save WAV as a timestamped file. Returns path."""
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # ms precision
    fname = f"recording_{ts}{suffix}.wav"
    path = RECORDINGS_DIR / fname
    path.write_bytes(wav_bytes)
    size_kb = len(wav_bytes) // 1024
    log.debug("Recording saved: %s (%d KB)", path.name, size_kb)
    return path


def delete_recording(path: Path) -> None:
    """Delete a backup after successful transcription."""
    if path is None:
        return
    try:
        path.unlink()
        log.debug("Recording deleted: %s", path.name)
    except FileNotFoundError:
        pass
    except Exception as ex:
        log.warning("Could not delete recording (%s): %s", path, ex)


def mark_failed(path: Path) -> Path:
    """Rename a recording with _failed suffix so the user notices it."""
    if path is None or not path.exists():
        return path
    new_name = path.stem + "_failed" + path.suffix
    new_path = path.with_name(new_name)
    try:
        path.rename(new_path)
        log.info("Recording marked as FAILED: %s", new_path.name)
        return new_path
    except Exception as ex:
        log.warning("Could not rename recording (%s): %s", path, ex)
        return path


def cleanup_old_recordings(max_age_days: int = RETENTION_DAYS) -> int:
    """Delete recordings older than max_age_days. Returns count of deleted files."""
    if not RECORDINGS_DIR.exists():
        return 0
    cutoff = datetime.now().timestamp() - max_age_days * 86400
    count = 0
    for f in RECORDINGS_DIR.glob("recording_*.wav"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                count += 1
        except Exception as ex:
            log.debug("Cleanup skip %s: %s", f, ex)
    if count > 0:
        log.info("Cleanup: deleted %d old recordings (>%dd).", count, max_age_days)
    return count


def list_pending_recordings() -> list[Path]:
    """List recordings — both normal and _failed-marked ones."""
    if not RECORDINGS_DIR.exists():
        return []
    return sorted(RECORDINGS_DIR.glob("recording_*.wav"))


def check_size_for_whisper(wav_bytes: bytes) -> tuple[bool, str]:
    """Check whether audio fits OpenAI's 25 MB limit.

    Returns (ok, message). If ok=False: > 25 MB, API will reject.
    """
    size = len(wav_bytes)
    if size > WHISPER_MAX_BYTES:
        return False, (
            f"Audio {size // 1024 // 1024} MB exceeds Whisper limit (25 MB). "
            f"Recording is still backed up to disk."
        )
    if size > WHISPER_WARN_BYTES:
        return True, f"Audio {size // 1024 // 1024} MB close to the 25 MB limit."
    return True, ""
