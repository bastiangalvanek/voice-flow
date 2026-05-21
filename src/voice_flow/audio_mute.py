"""Mute system audio during recording (Wispr-style).

Crash safety:
- atexit + signal handler: even if the process crashes or receives SIGINT/SIGTERM,
  audio is always unmuted. Prevents leaving the user with permanently silent output.
- CoInitialize per call: pycaw uses STA-bound COM interfaces. mute()/unmute() are
  called from the keyboard library thread (different from __init__).
- _we_muted flag: idempotency. Repeated mute() doesn't overwrite the original state;
  repeated unmute() after reset is a no-op.
"""
from __future__ import annotations

import atexit
import logging
import signal
import sys
import threading
from ctypes import POINTER, cast

log = logging.getLogger(__name__)

# Single instance for atexit hook (one process = one mute provider).
_GLOBAL_INSTANCE: "SystemAudioMute | None" = None


class SystemAudioMute:
    """Master output mute via Windows Core Audio API with crash safety."""

    def __init__(self) -> None:
        global _GLOBAL_INSTANCE

        self._available = False
        self._volume = None
        self._previous_mute: bool | None = None
        self._we_muted: bool = False
        self._call_lock = threading.Lock()
        self._co_inited_threads: set[int] = set()  # track threads that already CoInit'd

        if sys.platform != "win32":
            log.debug("Audio mute is Windows-only.")
            return

        try:
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        except ImportError as ex:
            log.warning("pycaw/comtypes not installed (%s) — audio mute disabled.", ex)
            return

        try:
            speakers = AudioUtilities.GetSpeakers()
            if hasattr(speakers, "_dev") and speakers._dev is not None:
                immdevice = speakers._dev
            elif hasattr(speakers, "Activate"):
                immdevice = speakers
            else:
                log.warning("Unknown pycaw API variant: %s", type(speakers).__name__)
                return

            interface = immdevice.Activate(
                IAudioEndpointVolume._iid_, CLSCTX_ALL, None
            )
            self._volume = cast(interface, POINTER(IAudioEndpointVolume))
            _ = self._volume.GetMute()  # smoke test
            self._available = True
            log.debug("Audio mute ready.")

            # Crash safety: atexit + signal handler, registered globally once.
            if _GLOBAL_INSTANCE is None:
                _GLOBAL_INSTANCE = self
                atexit.register(_atexit_emergency_unmute)
                _install_signal_handlers()
        except Exception as ex:
            log.warning("Could not initialize default audio endpoint: %s", ex)

    @property
    def available(self) -> bool:
        return self._available and self._volume is not None

    def _ensure_co_init(self) -> None:
        """CoInitialize for the current thread if not already done.

        pycaw COM calls from a foreign thread (e.g. keyboard library thread)
        need CoInitialize or behavior is undefined. Idempotent via thread-id set.
        """
        tid = threading.get_ident()
        if tid in self._co_inited_threads:
            return
        try:
            import comtypes
            comtypes.CoInitialize()
            self._co_inited_threads.add(tid)
            log.debug("CoInitialize for thread %d.", tid)
        except Exception as ex:
            log.debug("CoInitialize failed (maybe already initialized): %s", ex)
            self._co_inited_threads.add(tid)  # don't retry

    def mute(self) -> None:
        """Mute master output (idempotent via _we_muted flag)."""
        if not self.available:
            return
        with self._call_lock:
            if self._we_muted:
                # Already muted by us — don't overwrite _previous on double-mute.
                return
            self._ensure_co_init()
            try:
                self._previous_mute = bool(self._volume.GetMute())
                if not self._previous_mute:
                    self._volume.SetMute(1, None)
                    self._we_muted = True
                    log.debug("System audio muted (was on before).")
                else:
                    # Was already muted (DND, mute button) — we didn't mute it ourselves.
                    self._we_muted = False
            except Exception as ex:
                log.warning("Mute failed: %s", ex)

    def unmute(self) -> None:
        """Unmute if WE set the mute (respects DND)."""
        if not self.available:
            return
        with self._call_lock:
            if not self._we_muted:
                # We didn't mute (or already restored) — do nothing.
                self._previous_mute = None
                return
            self._ensure_co_init()
            try:
                self._volume.SetMute(0, None)
                log.debug("System audio restored.")
            except Exception as ex:
                log.warning("Unmute failed: %s", ex)
            finally:
                self._we_muted = False
                self._previous_mute = None

    def emergency_unmute(self) -> None:
        """For atexit/signal handler: unmute even if _we_muted is uncertain.

        On crash mid-mute()/unmute() the flag may be wrong. Better to unmute
        than to leave the system silent.
        """
        if not self.available:
            return
        try:
            self._ensure_co_init()
            current = bool(self._volume.GetMute())
            if current and self._we_muted:
                self._volume.SetMute(0, None)
                log.warning("EMERGENCY UNMUTE: system audio restored.")
            self._we_muted = False
        except Exception as ex:
            log.warning("Emergency unmute failed: %s", ex)


def _atexit_emergency_unmute() -> None:
    """atexit hook: ensures system isn't left permanently muted."""
    if _GLOBAL_INSTANCE is not None:
        try:
            _GLOBAL_INSTANCE.emergency_unmute()
        except Exception:
            pass


_signal_handlers_installed = False


def _install_signal_handlers() -> None:
    """Register signal handlers that call emergency_unmute + exit."""
    global _signal_handlers_installed
    if _signal_handlers_installed:
        return

    def _handler(signum, frame):
        log.warning("Signal %d received — emergency unmute + exit.", signum)
        _atexit_emergency_unmute()
        sys.exit(1)

    for sig_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError) as ex:
            log.debug("Could not install signal handler for %s: %s", sig_name, ex)

    _signal_handlers_installed = True
