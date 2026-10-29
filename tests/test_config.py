from __future__ import annotations

import pytest

from phantom_shell.config import Config


def test_default_config_is_loopback_gemma():
    config = Config()
    assert config.ollama_url == "http://localhost:11434"
    assert config.model == "gemma4:e4b"


def test_config_rejects_remote_ollama_endpoint(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[phantom]\nollama_url = "https://example.com"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="localhost"):
        Config.load(path)


def test_config_rejects_invalid_threshold_and_unknown_key(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[phantom]\ncpu_threshold = 101\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cpu_threshold"):
        Config.load(path)
    path.write_text("[phantom]\nunknown_switch = true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown configuration"):
        Config.load(path)


def test_boolean_environment_override_parses_false(monkeypatch, tmp_path):
    monkeypatch.setenv("PHANTOM_STORY_MODE", "false")
    config = Config.load(tmp_path / "missing.toml")
    assert config.story_mode is False
