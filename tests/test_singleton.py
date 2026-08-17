"""Tests for the port-based singleton lock + IPC.

We bind to ephemeral ports (port=0) so the tests don't collide with a running
Voice Flow instance on the default port (54381).
"""
from __future__ import annotations

import socket
import time

from voice_flow.singleton import SingletonLock


def _free_port() -> int:
    """Grab a free port from the OS and return it (small race window, fine for tests)."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_acquire_succeeds_when_port_is_free():
    port = _free_port()
    lock = SingletonLock(port=port)
    assert lock.acquire() is True
    lock.release()


def test_acquire_fails_when_port_is_taken():
    port = _free_port()
    first = SingletonLock(port=port)
    assert first.acquire() is True

    second = SingletonLock(port=port)
    assert second.acquire() is False  # cannot bind

    first.release()


def test_release_frees_the_port():
    port = _free_port()
    first = SingletonLock(port=port)
    first.acquire()
    first.release()

    # Give the OS a moment to actually free SO_EXCLUSIVEADDRUSE
    time.sleep(0.1)

    second = SingletonLock(port=port)
    assert second.acquire() is True
    second.release()


def test_send_command_to_running_instance():
    port = _free_port()
    lock = SingletonLock(port=port)
    assert lock.acquire() is True

    received: list[str] = []

    def handler(cmd: str) -> None:
        received.append(cmd)

    lock.set_command_handler(handler)
    # Give the accept-thread a moment to spin up
    time.sleep(0.1)

    ok = SingletonLock.send_command("ping", port=port, timeout=2.0)
    assert ok is True

    # Wait for handler to process
    deadline = time.time() + 2.0
    while time.time() < deadline and not received:
        time.sleep(0.02)

    assert received == ["ping"]
    lock.release()


def test_send_command_returns_false_when_nobody_listening():
    port = _free_port()  # nobody bound
    assert SingletonLock.send_command("anything", port=port, timeout=0.5) is False


def test_handler_exception_returns_err_response():
    port = _free_port()
    lock = SingletonLock(port=port)
    lock.acquire()

    def handler(cmd: str) -> None:
        raise RuntimeError("boom")

    lock.set_command_handler(handler)
    time.sleep(0.1)

    # send_command checks for "OK" prefix; an "ERR" response → returns False
    ok = SingletonLock.send_command("trigger", port=port, timeout=2.0)
    assert ok is False

    lock.release()


def test_release_is_idempotent():
    port = _free_port()
    lock = SingletonLock(port=port)
    lock.acquire()
    lock.release()
    lock.release()  # must not raise
