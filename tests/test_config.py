from dataclasses import replace

import pytest

from voice_flow.config import Config, load_config


def test_missing_openai_key_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("voice_flow.config.ENV_FILE", tmp_path / ".env-does-not-exist")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        load_config()


def test_load_config_with_key(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VOICE_FLOW_ENABLE_CLEANUP", raising=False)
    monkeypatch.setattr("voice_flow.config.ENV_FILE", tmp_path / ".env-does-not-exist")
    monkeypatch.setattr("voice_flow.config.CONTEXT_FILE", tmp_path / "no-context.txt")

    cfg = load_config()
    assert cfg.openai_api_key == "sk-test-123"
    assert cfg.anthropic_api_key is None
    assert cfg.cleanup_available is False
    assert cfg.hotkey == "f8"
    assert cfg.language == "auto"


def test_overrides_apply(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("VOICE_FLOW_ENABLE_CLEANUP", raising=False)
    monkeypatch.setattr("voice_flow.config.ENV_FILE", tmp_path / ".env-x")
    monkeypatch.setattr("voice_flow.config.CONTEXT_FILE", tmp_path / "ctx-x")

    cfg = load_config({"hotkey": "f9", "enable_tray": False})
    assert cfg.hotkey == "f9"
    assert cfg.enable_tray is False


def test_cleanup_available_requires_both(monkeypatch):
    # enable_cleanup defaults to False — explicitly enable for this test.
    base = Config(openai_api_key="x", anthropic_api_key="y", enable_cleanup=True)
    assert base.cleanup_available is True
    assert replace(base, enable_cleanup=False).cleanup_available is False
    assert replace(base, anthropic_api_key=None).cleanup_available is False
