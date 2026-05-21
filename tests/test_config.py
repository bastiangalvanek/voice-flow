from dataclasses import replace

import pytest

from voice_flow.config import (
    Config,
    _parse_bool_env,
    find_context_file,
    find_env_file,
    load_config,
)


def test_missing_openai_key_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VOICE_FLOW_ENABLE_CLEANUP", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "voice_flow.config._candidate_env_files",
        lambda: [tmp_path / ".env-does-not-exist"],
    )
    monkeypatch.setattr(
        "voice_flow.config._candidate_context_files",
        lambda: [tmp_path / "no-context.txt"],
    )
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        load_config()


def test_load_config_with_key(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VOICE_FLOW_ENABLE_CLEANUP", raising=False)
    monkeypatch.setattr(
        "voice_flow.config._candidate_env_files",
        lambda: [tmp_path / ".env-does-not-exist"],
    )
    monkeypatch.setattr(
        "voice_flow.config._candidate_context_files",
        lambda: [tmp_path / "no-context.txt"],
    )

    cfg = load_config()
    assert cfg.openai_api_key == "sk-test-123"
    assert cfg.anthropic_api_key is None
    assert cfg.cleanup_available is False
    assert cfg.hotkey == "f8"
    assert cfg.language == "auto"


def test_overrides_apply(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("VOICE_FLOW_ENABLE_CLEANUP", raising=False)
    monkeypatch.setattr(
        "voice_flow.config._candidate_env_files", lambda: [tmp_path / ".env-x"]
    )
    monkeypatch.setattr(
        "voice_flow.config._candidate_context_files", lambda: [tmp_path / "ctx-x"]
    )

    cfg = load_config({"hotkey": "f9", "enable_tray": False})
    assert cfg.hotkey == "f9"
    assert cfg.enable_tray is False


def test_cleanup_available_requires_both():
    base = Config(openai_api_key="x", anthropic_api_key="y", enable_cleanup=True)
    assert base.cleanup_available is True
    assert replace(base, enable_cleanup=False).cleanup_available is False
    assert replace(base, anthropic_api_key=None).cleanup_available is False


# ── _parse_bool_env (strict) ───────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1", True),
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("yes", True),
        ("YES", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("False", False),
        ("no", False),
        ("off", False),
        ("", False),
    ],
)
def test_parse_bool_env_known_values(monkeypatch, value, expected):
    monkeypatch.setenv("VF_TEST_FLAG", value)
    assert _parse_bool_env("VF_TEST_FLAG", default=False) is expected


def test_parse_bool_env_unknown_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("VF_TEST_FLAG", "maybe")
    assert _parse_bool_env("VF_TEST_FLAG", default=False) is False
    assert _parse_bool_env("VF_TEST_FLAG", default=True) is True


def test_parse_bool_env_unset_uses_default(monkeypatch):
    monkeypatch.delenv("VF_TEST_FLAG", raising=False)
    assert _parse_bool_env("VF_TEST_FLAG", default=False) is False
    assert _parse_bool_env("VF_TEST_FLAG", default=True) is True


# ── enable_cleanup wired through load_config ───────────────────────────


def test_enable_cleanup_env_true(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VOICE_FLOW_ENABLE_CLEANUP", "yes")
    monkeypatch.setattr(
        "voice_flow.config._candidate_env_files", lambda: [tmp_path / ".env-x"]
    )
    monkeypatch.setattr(
        "voice_flow.config._candidate_context_files", lambda: [tmp_path / "ctx-x"]
    )
    cfg = load_config()
    assert cfg.enable_cleanup is True
    assert cfg.cleanup_available is True


def test_enable_cleanup_env_false_default(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("VOICE_FLOW_ENABLE_CLEANUP", raising=False)
    monkeypatch.setattr(
        "voice_flow.config._candidate_env_files", lambda: [tmp_path / ".env-x"]
    )
    monkeypatch.setattr(
        "voice_flow.config._candidate_context_files", lambda: [tmp_path / "ctx-x"]
    )
    cfg = load_config()
    assert cfg.enable_cleanup is False


# ── env / context file lookup ──────────────────────────────────────────


def test_find_env_file_prefers_first_existing(monkeypatch, tmp_path):
    primary = tmp_path / "primary.env"
    secondary = tmp_path / "secondary.env"
    secondary.write_text("SECONDARY=1")

    monkeypatch.setattr(
        "voice_flow.config._candidate_env_files", lambda: [primary, secondary]
    )
    assert find_env_file() == secondary

    primary.write_text("PRIMARY=1")
    assert find_env_file() == primary


def test_find_env_file_returns_none_when_no_candidate_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "voice_flow.config._candidate_env_files",
        lambda: [tmp_path / "a", tmp_path / "b"],
    )
    assert find_env_file() is None


def test_find_context_file_lookup(monkeypatch, tmp_path):
    primary = tmp_path / "context.txt"
    secondary = tmp_path / "fallback.txt"
    monkeypatch.setattr(
        "voice_flow.config._candidate_context_files", lambda: [primary, secondary]
    )
    assert find_context_file() is None

    secondary.write_text("hello")
    assert find_context_file() == secondary

    primary.write_text("primary")
    assert find_context_file() == primary
