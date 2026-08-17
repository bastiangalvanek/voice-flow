"""Tests for the first-run wizard's file-writing logic.

We don't exercise the PyQt6 dialog itself in pytest (it needs a display).
write_env_file is pure I/O and can be unit-tested cleanly.
"""
from __future__ import annotations

from pathlib import Path

from voice_flow.first_run import write_env_file


def test_write_env_file_minimal(tmp_path: Path) -> None:
    target = tmp_path / "voice-flow" / ".env"
    written = write_env_file(openai_key="sk-test-123", target=target)

    assert written == target
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-test-123" in content
    assert "ANTHROPIC_API_KEY" not in content
    assert "VOICE_FLOW_ENABLE_CLEANUP" not in content


def test_write_env_file_with_anthropic(tmp_path: Path) -> None:
    target = tmp_path / ".env"
    write_env_file(
        openai_key="sk-1",
        anthropic_key="sk-ant-2",
        enable_cleanup=True,
        target=target,
    )
    content = target.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-1" in content
    assert "ANTHROPIC_API_KEY=sk-ant-2" in content
    assert "VOICE_FLOW_ENABLE_CLEANUP=1" in content


def test_write_env_file_anthropic_without_cleanup_flag(tmp_path: Path) -> None:
    target = tmp_path / ".env"
    write_env_file(
        openai_key="sk-1",
        anthropic_key="sk-ant-2",
        enable_cleanup=False,
        target=target,
    )
    content = target.read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY=sk-ant-2" in content
    assert "VOICE_FLOW_ENABLE_CLEANUP" not in content


def test_write_env_file_strips_whitespace(tmp_path: Path) -> None:
    target = tmp_path / ".env"
    write_env_file(
        openai_key="  sk-padded  ",
        anthropic_key="\nsk-ant-padded\n",
        enable_cleanup=True,
        target=target,
    )
    content = target.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-padded" in content
    assert "ANTHROPIC_API_KEY=sk-ant-padded" in content


def test_write_env_file_skips_empty_anthropic(tmp_path: Path) -> None:
    target = tmp_path / ".env"
    write_env_file(
        openai_key="sk-1",
        anthropic_key="   ",  # whitespace-only counts as empty
        enable_cleanup=True,  # but cleanup flag without key is silently dropped
        target=target,
    )
    content = target.read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY" not in content
    assert "VOICE_FLOW_ENABLE_CLEANUP" not in content


def test_write_env_file_creates_parent_dirs(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "c" / ".env"
    write_env_file(openai_key="sk-x", target=nested)
    assert nested.exists()
