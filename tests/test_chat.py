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


# ---------------------------------------------------------------------------
# Tool schema builder + dispatcher
# ---------------------------------------------------------------------------

def test_build_ollama_tools_returns_all_registry_tools():
    from bb.ai.chat import build_ollama_tools
    from bb.tools import TOOL_REGISTRY
    tools = build_ollama_tools()
    names = {t["function"]["name"] for t in tools}
    assert names == set(TOOL_REGISTRY.keys())


def test_build_ollama_tools_schema_shape():
    from bb.ai.chat import build_ollama_tools
    tools = build_ollama_tools()
    for tool in tools:
        assert tool["type"] == "function"
        assert "name" in tool["function"]
        assert "description" in tool["function"]
        assert tool["function"]["description"]  # non-empty
        assert "parameters" in tool["function"]
        assert tool["function"]["parameters"]["type"] == "object"


def test_dispatch_tool_known():
    """dispatch_tool calls a real tool function and returns JSON string."""
    import json
    from bb.ai.chat import dispatch_tool
    result = dispatch_tool("get_course_list", {})
    parsed = json.loads(result)
    assert isinstance(parsed, list)  # empty list when no DB, not an error


def test_dispatch_tool_unknown():
    import json
    from bb.ai.chat import dispatch_tool
    result = dispatch_tool("nonexistent_tool", {})
    parsed = json.loads(result)
    assert "error" in parsed


def test_dispatch_tool_graceful_when_db_missing(tmp_path, monkeypatch):
    """Tool returns empty list (not exception) when DB doesn't exist."""
    import json
    monkeypatch.setattr("bb.config.BB_DIR", tmp_path)
    from bb.ai.chat import dispatch_tool
    result = dispatch_tool("get_upcoming_deadlines", {"days": 7})
    parsed = json.loads(result)
    assert parsed == []  # graceful empty, not an error


# ---------------------------------------------------------------------------
# Ollama provider
# ---------------------------------------------------------------------------

def test_is_available_false_when_ollama_not_installed(monkeypatch):
    """is_available() returns False when ollama package is missing."""
    import sys
    import importlib
    monkeypatch.setitem(sys.modules, "ollama", None)
    # Force reimport of provider module without cached version
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)
    from bb.ai.providers.ollama import is_available
    assert is_available() is False


def test_is_available_false_when_server_unreachable(monkeypatch):
    """is_available() returns False when Ollama server is not running."""
    import sys
    from unittest.mock import MagicMock
    mock_ollama = MagicMock()
    mock_ollama.list.side_effect = Exception("connection refused")
    monkeypatch.setitem(sys.modules, "ollama", mock_ollama)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)
    from bb.ai.providers.ollama import is_available
    assert is_available() is False


def test_is_available_true_when_server_running(monkeypatch):
    """is_available() returns True when Ollama server responds."""
    import sys
    from unittest.mock import MagicMock
    mock_ollama = MagicMock()
    mock_ollama.list.return_value = MagicMock(models=[])
    monkeypatch.setitem(sys.modules, "ollama", mock_ollama)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)
    from bb.ai.providers.ollama import is_available
    assert is_available() is True


def test_get_model_exact_match_first(monkeypatch):
    """get_model() returns exact preferred model when available."""
    import sys
    from unittest.mock import MagicMock
    m1, m2 = MagicMock(), MagicMock()
    m1.model = "qwen3:8b"
    m2.model = "qwen3:30b-a3b"
    mock_ollama = MagicMock()
    mock_ollama.list.return_value = MagicMock(models=[m1, m2])
    monkeypatch.setitem(sys.modules, "ollama", mock_ollama)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)
    from bb.ai.providers.ollama import get_model
    assert get_model("qwen3:30b-a3b") == "qwen3:30b-a3b"


def test_get_model_falls_back_to_base_prefix(monkeypatch):
    """get_model() matches by base name when exact preferred not available."""
    import sys
    from unittest.mock import MagicMock
    m1 = MagicMock()
    m1.model = "qwen3:8b"
    mock_ollama = MagicMock()
    mock_ollama.list.return_value = MagicMock(models=[m1])
    monkeypatch.setitem(sys.modules, "ollama", mock_ollama)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)
    from bb.ai.providers.ollama import get_model
    # Preferred not present, but qwen3 base exists
    result = get_model("qwen3:30b-a3b")
    assert result == "qwen3:8b"


def test_get_model_uses_default_priority_when_no_preference(monkeypatch):
    """get_model() picks from default priority list when preferred is empty."""
    import sys
    from unittest.mock import MagicMock
    m1 = MagicMock()
    m1.model = "qwen2.5:7b"
    mock_ollama = MagicMock()
    mock_ollama.list.return_value = MagicMock(models=[m1])
    monkeypatch.setitem(sys.modules, "ollama", mock_ollama)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)
    from bb.ai.providers.ollama import get_model
    assert get_model("") == "qwen2.5:7b"


def test_get_model_returns_none_when_no_suitable_model(monkeypatch):
    """get_model() returns None when no known model is available."""
    import sys
    from unittest.mock import MagicMock
    m1 = MagicMock()
    m1.model = "some-unknown-model:latest"
    mock_ollama = MagicMock()
    mock_ollama.list.return_value = MagicMock(models=[m1])
    monkeypatch.setitem(sys.modules, "ollama", mock_ollama)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)
    from bb.ai.providers.ollama import get_model
    assert get_model("") is None
