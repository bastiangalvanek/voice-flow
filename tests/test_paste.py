"""Tests for the clipboard-based paste helper.

We mock `keyboard` and `pyperclip` so the tests don't actually move keys or
touch the system clipboard.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fake_clipboard(monkeypatch):
    """Replace pyperclip + keyboard with mocks. Returns (paste_mod, mocks)."""
    fake_pyperclip = types.ModuleType("pyperclip")
    fake_pyperclip.copy = MagicMock()
    fake_pyperclip.paste = MagicMock(return_value="OLD_CLIPBOARD")
    monkeypatch.setitem(sys.modules, "pyperclip", fake_pyperclip)

    fake_keyboard = types.ModuleType("keyboard")
    fake_keyboard.send = MagicMock()
    monkeypatch.setitem(sys.modules, "keyboard", fake_keyboard)

    # Force fresh import so the mocks are picked up by paste.py
    sys.modules.pop("voice_flow.paste", None)
    import voice_flow.paste as paste_mod

    # Reduce sleeps so the test suite stays fast
    monkeypatch.setattr(paste_mod, "PRE_PASTE_DELAY_SEC", 0)
    monkeypatch.setattr(paste_mod, "POST_PASTE_DELAY_SEC", 0)

    return paste_mod, fake_pyperclip, fake_keyboard


def test_paste_copies_and_sends_ctrl_v(fake_clipboard):
    paste_mod, pyperclip, keyboard = fake_clipboard
    paste_mod.paste_to_active_window("hello", restore_clipboard=False)
    pyperclip.copy.assert_called_with("hello")
    keyboard.send.assert_called_with("ctrl+v")


def test_paste_without_restore_does_not_read_old(fake_clipboard):
    paste_mod, pyperclip, _ = fake_clipboard
    paste_mod.paste_to_active_window("hi", restore_clipboard=False)
    pyperclip.paste.assert_not_called()


def test_paste_with_restore_writes_then_restores(fake_clipboard):
    paste_mod, pyperclip, _ = fake_clipboard
    paste_mod.paste_to_active_window("new", restore_clipboard=True)
    # Two copy calls: first the text, then the restore
    assert pyperclip.copy.call_args_list[0].args == ("new",)
    assert pyperclip.copy.call_args_list[-1].args == ("OLD_CLIPBOARD",)


def test_paste_skips_restore_when_old_is_image(fake_clipboard):
    paste_mod, pyperclip, _ = fake_clipboard
    pyperclip.paste.return_value = ""  # pyperclip returns "" for non-text clipboards
    paste_mod.paste_to_active_window("new", restore_clipboard=True)
    # Only one copy call (the text), no restore
    copy_calls = [c.args[0] for c in pyperclip.copy.call_args_list]
    assert copy_calls == ["new"]


def test_paste_skips_restore_when_read_fails(fake_clipboard):
    paste_mod, pyperclip, _ = fake_clipboard
    pyperclip.paste.side_effect = RuntimeError("clipboard busy")
    paste_mod.paste_to_active_window("new", restore_clipboard=True)
    # paste failed → only the text copy, no restore
    copy_calls = [c.args[0] for c in pyperclip.copy.call_args_list]
    assert copy_calls == ["new"]


def test_paste_raises_when_copy_fails(fake_clipboard):
    paste_mod, pyperclip, _ = fake_clipboard
    pyperclip.copy.side_effect = OSError("clipboard locked")
    with pytest.raises(OSError, match="clipboard locked"):
        paste_mod.paste_to_active_window("x")


def test_paste_restore_failure_is_swallowed(fake_clipboard):
    """If the restore copy fails, we don't crash — original text is already in place."""
    paste_mod, pyperclip, _ = fake_clipboard

    def copy_then_raise(text):
        # First call succeeds; second (restore) raises
        if pyperclip.copy.call_count >= 2:
            raise OSError("restore busted")

    pyperclip.copy.side_effect = copy_then_raise
    # Must NOT raise — the user's text was already pasted
    paste_mod.paste_to_active_window("new", restore_clipboard=True)
