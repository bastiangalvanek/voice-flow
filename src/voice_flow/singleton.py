"""Port-based singleton lock with IPC.

Binds a TCP socket to 127.0.0.1:PORT. While the process runs, the port is
occupied — a second Voice Flow process cannot bind.

The lock socket also accepts incoming connections and reads short text commands.
A second instance can send commands to the first (e.g. "show_ready" to re-display
the ready pill instead of silently popping a MessageBox).

Protocol: ASCII command + newline. Max 64 bytes. Response: "OK\\n" or "ERR\\n".
"""
from __future__ import annotations

import logging
import socket
import sys
import threading
from typing import Callable, Optional

log = logging.getLogger(__name__)

LOCK_PORT = 54381
RECV_BUF = 64
ACCEPT_TIMEOUT_SEC = 0.5


class SingletonLock:
    def __init__(self, port: int = LOCK_PORT):
        self.port = port
        self._sock: socket.socket | None = None
        self._command_handler: Optional[Callable[[str], None]] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def acquire(self) -> bool:
        """Returns True if lock acquired, False if Voice Flow already running."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if sys.platform == "win32":
                SO_EXCLUSIVEADDRUSE = getattr(socket, "SO_EXCLUSIVEADDRUSE", -5)
                sock.setsockopt(socket.SOL_SOCKET, SO_EXCLUSIVEADDRUSE, 1)
        except Exception as ex:
            log.debug("SO_EXCLUSIVEADDRUSE could not be set: %s", ex)

        try:
            sock.bind(("127.0.0.1", self.port))
            sock.listen(4)
            sock.settimeout(ACCEPT_TIMEOUT_SEC)
        except OSError:
            sock.close()
            log.warning("Voice Flow already running (port %d in use).", self.port)
            return False
        self._sock = sock
        log.debug("Singleton lock acquired on port %d.", self.port)
        return True

    def set_command_handler(self, handler: Callable[[str], None]) -> None:
        """Register handler for incoming IPC commands from second instances."""
        self._command_handler = handler
        if self._sock is not None and self._accept_thread is None:
            self._accept_thread = threading.Thread(
                target=self._accept_loop, daemon=True, name="singleton-ipc"
            )
            self._accept_thread.start()

    def _accept_loop(self) -> None:
        assert self._sock is not None
        while not self._stop_event.is_set():
            try:
                conn, _addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                conn.settimeout(0.5)
                data = conn.recv(RECV_BUF)
                cmd = data.decode("utf-8", errors="replace").strip()
                log.debug("IPC received: %r", cmd)
                if cmd and self._command_handler:
                    try:
                        self._command_handler(cmd)
                        conn.sendall(b"OK\n")
                    except Exception as ex:
                        log.warning("IPC handler error: %s", ex)
                        conn.sendall(b"ERR\n")
                else:
                    conn.sendall(b"ERR\n")
            except Exception as ex:
                log.debug("IPC connection error: %s", ex)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def release(self) -> None:
        self._stop_event.set()
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    @staticmethod
    def send_command(command: str, port: int = LOCK_PORT, timeout: float = 1.0) -> bool:
        """Send a command to the running Voice Flow instance.

        Called by the second instance when the lock is blocked.
        Returns True on "OK" response, False otherwise.
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect(("127.0.0.1", port))
            s.sendall((command + "\n").encode("utf-8"))
            resp = s.recv(RECV_BUF).decode("utf-8", errors="replace").strip()
            s.close()
            return resp.startswith("OK")
        except Exception as ex:
            log.warning("IPC send '%s' failed: %s", command, ex)
            return False
