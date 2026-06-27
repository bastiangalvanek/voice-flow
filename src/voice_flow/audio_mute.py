"""System-Audio waehrend Recording muten (Wispr-Style).

Critic-Findings P0-1, P1-6, P1-7 adressiert:
- atexit + signal-handler: wenn Process crasht oder via SIGINT/SIGTERM endet,
  wird IMMER unmuted. Verhindert dass Bastian mit dauerhaft stummen
  Kopfhoerern dasteht (Worst-Case: reboot oder manuell lautsprecher-icon).
- CoInitialize pro Call: pycaw nutzt STA-bound COM-Interfaces. mute()/unmute()
  werden aus dem keyboard-Library-Thread aufgerufen (anderer Thread als __init__).
- _we_muted Flag: Idempotenz. Mehrfaches mute() ueberschreibt nicht den
  Original-State, mehrfaches unmute() nach Reset macht nichts dummes.
"""
from __future__ import annotations

import atexit
import logging
import signal
import sys
import threading
from ctypes import POINTER, cast

log = logging.getLogger(__name__)

# Single instance fuer atexit-Hook (nur ein Process = nur ein Mute-Provider)
_GLOBAL_INSTANCE: "SystemAudioMute | None" = None


class SystemAudioMute:
    """Master-Output-Mute via Windows Core Audio API mit Crash-Safety."""

    def __init__(self) -> None:
        global _GLOBAL_INSTANCE

        self._available = False
        self._volume = None
        self._previous_mute: bool | None = None
        self._we_muted: bool = False
        self._call_lock = threading.Lock()
        self._co_inited_threads: set[int] = set()  # Track welche threads bereits CoInit haben

        if sys.platform != "win32":
            log.debug("Audio-Mute nur auf Windows verfuegbar.")
            return

        try:
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        except ImportError as ex:
            log.warning("pycaw/comtypes nicht installiert (%s) - Audio-Mute deaktiviert", ex)
            return

        try:
            speakers = AudioUtilities.GetSpeakers()
            if hasattr(speakers, "_dev") and speakers._dev is not None:
                immdevice = speakers._dev
            elif hasattr(speakers, "Activate"):
                immdevice = speakers
            else:
                log.warning("Unbekannte pycaw-API-Variante: %s", type(speakers).__name__)
                return

            interface = immdevice.Activate(
                IAudioEndpointVolume._iid_, CLSCTX_ALL, None
            )
            self._volume = cast(interface, POINTER(IAudioEndpointVolume))
            _ = self._volume.GetMute()  # Smoke-Test
            self._available = True
            log.debug("Audio-Mute bereit.")

            # ── Crash-Safety: atexit + signal handler ────────────────────
            # Nur global EINMAL registrieren, sonst chain mehrfach.
            if _GLOBAL_INSTANCE is None:
                _GLOBAL_INSTANCE = self
                atexit.register(_atexit_emergency_unmute)
                _install_signal_handlers()
        except Exception as ex:
            log.warning("Konnte Default-Audio-Endpoint nicht initialisieren: %s", ex)

    @property
    def available(self) -> bool:
        return self._available and self._volume is not None

    def _ensure_co_init(self) -> None:
        """CoInitialize fuer aktuellen Thread wenn noch nicht passiert.

        pycaw COM-Calls von einem fremden Thread (z.B. keyboard library thread)
        brauchen CoInitialize sonst undefined behavior. Idempotent via thread-id-set.
        """
        tid = threading.get_ident()
        if tid in self._co_inited_threads:
            return
        try:
            import comtypes
            comtypes.CoInitialize()
            self._co_inited_threads.add(tid)
            log.debug("CoInitialize fuer thread %d.", tid)
        except Exception as ex:
            log.debug("CoInitialize failed (vielleicht schon initialisiert): %s", ex)
            self._co_inited_threads.add(tid)  # nicht nochmal versuchen

    def mute(self) -> None:
        """Mutet Master-Output (idempotent dank _we_muted Flag)."""
        if not self.available:
            return
        with self._call_lock:
            if self._we_muted:
                # Schon von uns gemuted — kein doppeltes mute (sonst _previous wird ueberschrieben)
                return
            self._ensure_co_init()
            try:
                self._previous_mute = bool(self._volume.GetMute())
                if not self._previous_mute:
                    self._volume.SetMute(1, None)
                    self._we_muted = True
                    log.debug("System-Audio gemuted (war vorher an).")
                else:
                    # War schon gemuted (DND, Mute-Button) — wir nicht selbst gemuted
                    self._we_muted = False
            except Exception as ex:
                log.warning("Mute fehlgeschlagen: %s", ex)

    def unmute(self) -> None:
        """Unmutet wenn WIR den Mute gesetzt haben (respektiert DND)."""
        if not self.available:
            return
        with self._call_lock:
            if not self._we_muted:
                # Wir haben nicht gemuted (oder schon zurueckgenommen) — nichts tun
                self._previous_mute = None
                return
            self._ensure_co_init()
            try:
                self._volume.SetMute(0, None)
                log.debug("System-Audio wieder aktiv.")
            except Exception as ex:
                log.warning("Unmute fehlgeschlagen: %s", ex)
            finally:
                self._we_muted = False
                self._previous_mute = None

    def emergency_unmute(self) -> None:
        """Fuer atexit/signal-handler: unmute auch wenn _we_muted unsicher ist.

        Bei Crash mitten in mute()/unmute() kann der Flag falsch sein.
        Bei emergency lieber unmuten als stumm zu lassen.
        """
        if not self.available:
            return
        try:
            self._ensure_co_init()
            current = bool(self._volume.GetMute())
            if current and self._we_muted:
                self._volume.SetMute(0, None)
                log.warning("EMERGENCY UNMUTE: System-Audio wieder aktiv.")
            self._we_muted = False
        except Exception as ex:
            log.warning("Emergency unmute fehlgeschlagen: %s", ex)


def _atexit_emergency_unmute() -> None:
    """atexit-Hook: stellt sicher dass System nicht dauerhaft stumm bleibt."""
    if _GLOBAL_INSTANCE is not None:
        try:
            _GLOBAL_INSTANCE.emergency_unmute()
        except Exception:
            pass


_signal_handlers_installed = False


def _install_signal_handlers() -> None:
    """Registriert signal-handler die emergency_unmute aufrufen + exit."""
    global _signal_handlers_installed
    if _signal_handlers_installed:
        return

    def _handler(signum, frame):
        log.warning("Signal %d empfangen — emergency unmute + exit.", signum)
        _atexit_emergency_unmute()
        sys.exit(1)

    for sig_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError) as ex:
            log.debug("Konnte signal-handler fuer %s nicht setzen: %s", sig_name, ex)

    _signal_handlers_installed = True
