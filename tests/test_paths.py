"""Tests for the PyInstaller-aware path helpers in config.py.

These cover code paths that pytest can't normally exercise (frozen mode is only
true inside a real PyInstaller bundle) — we monkeypatch sys.frozen and
sys.executable instead.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

import voice_flow.config as cfg_mod

# ── _is_frozen ─────────────────────────────────────────────────────────


def test_is_frozen_false_by_default(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert cfg_mod._is_frozen() is False


def test_is_frozen_true_when_attribute_set(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert cfg_mod._is_frozen() is True


def test_is_frozen_false_when_attribute_falsy(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert cfg_mod._is_frozen() is False


# ── _project_root ──────────────────────────────────────────────────────


def test_project_root_source_mode(monkeypatch):
    """In source mode, project root is two levels above config.py."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    root = cfg_mod._project_root()
    assert (root / "src" / "voice_flow" / "config.py").exists() or (
        root / "voice_flow" / "config.py"
    ).exists()


def test_project_root_frozen_mode(monkeypatch, tmp_path):
    """In frozen mode, project root is the folder that contains the EXE."""
    fake_exe = tmp_path / "voice-flow.exe"
    fake_exe.write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    assert cfg_mod._project_root() == tmp_path.resolve()


# ── _user_config_dir ───────────────────────────────────────────────────


def test_user_config_dir_windows_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert cfg_mod._user_config_dir() == tmp_path / "voice-flow"


def test_user_config_dir_windows_fallback_when_no_appdata(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("APPDATA", raising=False)
    result = cfg_mod._user_config_dir()
    assert result == Path.home() / ".voice-flow"


@pytest.mark.parametrize("platform", ["linux", "darwin", "freebsd"])
def test_user_config_dir_non_windows(monkeypatch, platform):
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.delenv("APPDATA", raising=False)
    assert cfg_mod._user_config_dir() == Path.home() / ".voice-flow"


# ── lookup chain order ─────────────────────────────────────────────────


def test_candidate_env_files_ordering(monkeypatch, tmp_path):
    """Repo/EXE root must come before USER_CONFIG_DIR — local overrides win."""
    project_root = tmp_path / "project"
    user_dir = tmp_path / "user"
    monkeypatch.setattr(cfg_mod, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(cfg_mod, "USER_CONFIG_DIR", user_dir)

    candidates = cfg_mod._candidate_env_files()
    assert candidates[0] == project_root / ".env"
    assert candidates[1] == user_dir / ".env"


def test_candidate_context_files_ordering(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    user_dir = tmp_path / "user"
    monkeypatch.setattr(cfg_mod, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(cfg_mod, "USER_CONFIG_DIR", user_dir)

    candidates = cfg_mod._candidate_context_files()
    assert candidates[0] == project_root / "context.txt"
    assert candidates[1] == user_dir / "context.txt"
