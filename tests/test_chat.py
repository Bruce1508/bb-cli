"""Tests for bb chat AI layer."""
from __future__ import annotations


def test_aiconfig_defaults():
    from bb.config import AIConfig
    cfg = AIConfig()
    assert cfg.provider == "ollama"
    assert cfg.model == ""
    assert cfg.think is False


def test_bbconfig_has_ai_field():
    from bb.config import BBConfig
    cfg = BBConfig()
    assert hasattr(cfg, "ai")
    assert cfg.ai.provider == "ollama"


def test_bbconfig_loads_without_ai_section(tmp_path, monkeypatch):
    """Existing config.toml with no [ai] section loads with defaults."""
    import tomli_w
    monkeypatch.setattr("bb.config.BB_DIR", tmp_path)
    config_path = tmp_path / "config.toml"
    raw = tomli_w.dumps({"lms_type": "blackboard_ultra", "lms_url": "https://example.com"})
    config_path.write_bytes(raw if isinstance(raw, bytes) else raw.encode())
    from bb.config import load_config
    cfg = load_config()
    assert cfg.ai.provider == "ollama"
    assert cfg.ai.think is False
