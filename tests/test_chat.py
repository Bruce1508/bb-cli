"""Tests for bb chat AI layer."""
from __future__ import annotations

import json


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
    monkeypatch.setattr("bb.db.BB_DIR", tmp_path)
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


# ---------------------------------------------------------------------------
# ChatEngine
# ---------------------------------------------------------------------------

def _make_engine(monkeypatch, model: str = "qwen3:8b"):
    """Return a ChatEngine with mocked provider detection."""
    import sys
    from unittest.mock import MagicMock
    from bb.config import BBConfig
    mock_ollama_pkg = MagicMock()
    m1 = MagicMock()
    m1.model = model
    mock_ollama_pkg.list.return_value = MagicMock(models=[m1])
    monkeypatch.setitem(sys.modules, "ollama", mock_ollama_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)
    from bb.ai.chat import ChatEngine
    return ChatEngine(BBConfig()), mock_ollama_pkg


def test_chat_engine_detects_ollama_provider(monkeypatch):
    engine, _ = _make_engine(monkeypatch)
    assert engine.provider == "ollama"
    assert engine.model == "qwen3:8b"


def test_chat_engine_none_provider_when_unavailable(monkeypatch):
    import sys
    from unittest.mock import MagicMock
    from bb.config import BBConfig
    mock_ollama_pkg = MagicMock()
    mock_ollama_pkg.list.side_effect = Exception("not running")
    monkeypatch.setitem(sys.modules, "ollama", mock_ollama_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)
    from bb.ai.chat import ChatEngine
    engine = ChatEngine(BBConfig())
    assert engine.provider == "none"


def test_chat_engine_clear_history(monkeypatch):
    engine, _ = _make_engine(monkeypatch)
    engine._msgs.append({"role": "user", "content": "hello"})
    engine.clear_history()
    assert len(engine._msgs) == 1
    assert engine._msgs[0]["role"] == "system"


def test_chat_engine_get_provider_display(monkeypatch):
    engine, _ = _make_engine(monkeypatch)
    display = engine.get_provider_display()
    assert "ollama" in display
    assert "qwen3:8b" in display


def test_chat_engine_get_provider_display_think_on(monkeypatch):
    engine, _ = _make_engine(monkeypatch)
    engine._cfg.ai.think = True
    display = engine.get_provider_display()
    assert "think=on" in display


def test_process_turn_no_provider(monkeypatch):
    import sys
    from unittest.mock import MagicMock
    from bb.config import BBConfig
    mock_ollama_pkg = MagicMock()
    mock_ollama_pkg.list.side_effect = Exception("not running")
    monkeypatch.setitem(sys.modules, "ollama", mock_ollama_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)
    from bb.ai.chat import ChatEngine
    engine = ChatEngine(BBConfig())
    result = engine.process_turn("hello")
    assert "Ollama" in result or "provider" in result.lower()


def test_ollama_turn_plain_response(monkeypatch):
    """process_turn returns text when LLM responds without tool calls."""
    import sys
    from unittest.mock import MagicMock
    from bb.config import BBConfig

    mock_msg = MagicMock()
    mock_msg.content = "You have 3 upcoming deadlines."
    mock_msg.tool_calls = None

    mock_response = MagicMock()
    mock_response.message = mock_msg

    mock_ollama_pkg = MagicMock()
    m1 = MagicMock()
    m1.model = "qwen3:8b"
    mock_ollama_pkg.list.return_value = MagicMock(models=[m1])
    mock_ollama_pkg.chat.return_value = mock_response

    monkeypatch.setitem(sys.modules, "ollama", mock_ollama_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)

    from bb.ai.chat import ChatEngine
    engine = ChatEngine(BBConfig())
    result = engine.process_turn("what are my deadlines?")
    assert result == "You have 3 upcoming deadlines."


def test_ollama_turn_tool_call_dispatched(monkeypatch):
    """process_turn executes tool calls and returns final LLM response."""
    import sys
    from unittest.mock import MagicMock, call
    from bb.config import BBConfig

    # First response: has a tool call
    tc = MagicMock()
    tc.function.name = "get_course_list"
    tc.function.arguments = {}

    msg_with_tool = MagicMock()
    msg_with_tool.content = ""
    msg_with_tool.tool_calls = [tc]

    # Second response: plain text after tool result injected
    msg_final = MagicMock()
    msg_final.content = "Your courses are: BTP200, OPS445."
    msg_final.tool_calls = None

    mock_ollama_pkg = MagicMock()
    m1 = MagicMock()
    m1.model = "qwen3:8b"
    mock_ollama_pkg.list.return_value = MagicMock(models=[m1])
    mock_ollama_pkg.chat.side_effect = [
        MagicMock(message=msg_with_tool),
        MagicMock(message=msg_final),
    ]

    monkeypatch.setitem(sys.modules, "ollama", mock_ollama_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)

    from bb.ai.chat import ChatEngine
    engine = ChatEngine(BBConfig())
    result = engine.process_turn("list my courses")

    assert result == "Your courses are: BTP200, OPS445."
    assert mock_ollama_pkg.chat.call_count == 2
    # A tool result message should be in history
    roles = [m["role"] for m in engine._msgs]
    assert "tool" in roles


# ---------------------------------------------------------------------------
# run_chat() — single-shot and no-provider paths
# ---------------------------------------------------------------------------

def _make_mock_ollama_module(model: str = "qwen3:8b", response_text: str = "answer"):
    """Return a mock ollama module that returns response_text on chat()."""
    from unittest.mock import MagicMock
    mock_msg = MagicMock()
    mock_msg.content = response_text
    mock_msg.tool_calls = None
    m1 = MagicMock()
    m1.model = model
    mock_pkg = MagicMock()
    mock_pkg.list.return_value = MagicMock(models=[m1])
    mock_pkg.chat.return_value = MagicMock(message=mock_msg)
    return mock_pkg


def test_run_chat_single_shot_prints_response(monkeypatch, capsys):
    """Single-shot mode prints the LLM response and returns."""
    import sys
    from io import StringIO
    from rich.console import Console
    mock_pkg = _make_mock_ollama_module(response_text="3 deadlines coming up.")
    monkeypatch.setitem(sys.modules, "ollama", mock_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)

    buf = StringIO()
    con = Console(file=buf, highlight=False)
    from bb.ai.chat import run_chat
    from bb.config import BBConfig
    run_chat(query="how many deadlines?", cfg=BBConfig(), console=con)
    output = buf.getvalue()
    assert "3 deadlines coming up." in output


def test_run_chat_no_provider_prints_warning(monkeypatch):
    """When Ollama is unavailable, run_chat prints a warning and returns."""
    import sys
    from io import StringIO
    from unittest.mock import MagicMock
    from rich.console import Console
    mock_pkg = MagicMock()
    mock_pkg.list.side_effect = Exception("not running")
    monkeypatch.setitem(sys.modules, "ollama", mock_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)

    buf = StringIO()
    con = Console(file=buf, highlight=False)
    from bb.ai.chat import run_chat
    from bb.config import BBConfig
    run_chat(cfg=BBConfig(), console=con)
    output = buf.getvalue()
    assert "Ollama" in output or "ollama" in output.lower()


def test_handle_slash_exit_returns_true(monkeypatch):
    """/exit slash command signals REPL to exit."""
    import sys
    from unittest.mock import MagicMock
    mock_pkg = MagicMock()
    m1 = MagicMock()
    m1.model = "qwen3:8b"
    mock_pkg.list.return_value = MagicMock(models=[m1])
    monkeypatch.setitem(sys.modules, "ollama", mock_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)
    from bb.ai.chat import ChatEngine, _handle_slash
    from bb.config import BBConfig
    from io import StringIO
    from rich.console import Console
    engine = ChatEngine(BBConfig())
    con = Console(file=StringIO(), highlight=False)
    assert _handle_slash("/exit", engine, con) is True
    assert _handle_slash("/quit", engine, con) is True


def test_handle_slash_clear_resets_history(monkeypatch):
    """/clear resets conversation history."""
    import sys
    from unittest.mock import MagicMock
    mock_pkg = MagicMock()
    m1 = MagicMock()
    m1.model = "qwen3:8b"
    mock_pkg.list.return_value = MagicMock(models=[m1])
    monkeypatch.setitem(sys.modules, "ollama", mock_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)
    from bb.ai.chat import ChatEngine, _handle_slash
    from bb.config import BBConfig
    from io import StringIO
    from rich.console import Console
    engine = ChatEngine(BBConfig())
    engine._msgs.append({"role": "user", "content": "hello"})
    con = Console(file=StringIO(), highlight=False)
    result = _handle_slash("/clear", engine, con)
    assert result is False
    assert len(engine._msgs) == 1  # only system message remains


def test_handle_slash_think_toggles(monkeypatch):
    """/think toggles engine._cfg.ai.think."""
    import sys
    from unittest.mock import MagicMock
    mock_pkg = MagicMock()
    m1 = MagicMock()
    m1.model = "qwen3:8b"
    mock_pkg.list.return_value = MagicMock(models=[m1])
    monkeypatch.setitem(sys.modules, "ollama", mock_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)
    from bb.ai.chat import ChatEngine, _handle_slash
    from bb.config import BBConfig
    from io import StringIO
    from rich.console import Console
    engine = ChatEngine(BBConfig())
    assert engine._cfg.ai.think is False
    con = Console(file=StringIO(), highlight=False)
    _handle_slash("/think", engine, con)
    assert engine._cfg.ai.think is True
    _handle_slash("/think", engine, con)
    assert engine._cfg.ai.think is False


def test_handle_slash_unknown_returns_false(monkeypatch):
    """/unknown command returns False (no exit)."""
    import sys
    from unittest.mock import MagicMock
    mock_pkg = MagicMock()
    m1 = MagicMock()
    m1.model = "qwen3:8b"
    mock_pkg.list.return_value = MagicMock(models=[m1])
    monkeypatch.setitem(sys.modules, "ollama", mock_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)
    from bb.ai.chat import ChatEngine, _handle_slash
    from bb.config import BBConfig
    from io import StringIO
    from rich.console import Console
    engine = ChatEngine(BBConfig())
    con = Console(file=StringIO(), highlight=False)
    assert _handle_slash("/frobnicate", engine, con) is False


# ---------------------------------------------------------------------------
# CLI integration — bb chat command
# ---------------------------------------------------------------------------

def test_cli_chat_command_exists():
    """bb chat command is registered in the Typer app."""
    from typer.testing import CliRunner
    from bb.cli import app
    runner = CliRunner()
    result = runner.invoke(app, ["chat", "--help"])
    assert result.exit_code == 0
    assert "chat" in result.output.lower() or "query" in result.output.lower()


def test_cli_chat_single_shot_no_ollama(monkeypatch, tmp_path):
    """bb chat 'q' prints Ollama-unavailable message gracefully."""
    import sys
    from unittest.mock import MagicMock, patch
    from typer.testing import CliRunner
    mock_pkg = MagicMock()
    mock_pkg.list.side_effect = Exception("not running")
    monkeypatch.setitem(sys.modules, "ollama", mock_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)
    with patch("bb.config.BB_DIR", tmp_path), patch("bb.db.BB_DIR", tmp_path):
        from bb.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["chat", "hello"])
    assert result.exit_code == 0
    assert "ollama" in result.output.lower() or "Ollama" in result.output


def test_ollama_turn_max_tool_rounds_exhausted(monkeypatch):
    """Engine returns limit message and appends it to history after MAX_TOOL_ROUNDS."""
    import sys
    from unittest.mock import MagicMock
    from bb.config import BBConfig
    from bb.ai.chat import MAX_TOOL_ROUNDS

    # Every response always has a tool call — forces loop to exhaust
    tc = MagicMock()
    tc.function.name = "get_course_list"
    tc.function.arguments = {}
    msg_with_tool = MagicMock()
    msg_with_tool.content = ""
    msg_with_tool.tool_calls = [tc]

    mock_ollama_pkg = MagicMock()
    m1 = MagicMock()
    m1.model = "qwen3:8b"
    mock_ollama_pkg.list.return_value = MagicMock(models=[m1])
    mock_ollama_pkg.chat.return_value = MagicMock(message=msg_with_tool)

    monkeypatch.setitem(sys.modules, "ollama", mock_ollama_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)

    from bb.ai.chat import ChatEngine
    engine = ChatEngine(BBConfig())
    result = engine.process_turn("loop forever")

    assert "limit" in result.lower()
    assert mock_ollama_pkg.chat.call_count == MAX_TOOL_ROUNDS
    # The limit message must be recorded in history so the next turn sees it
    assert engine._msgs[-1] == {"role": "assistant", "content": result}


def test_handle_slash_sync(monkeypatch):
    """/sync calls subprocess with sys.executable and reports success/failure."""
    import sys
    from io import StringIO
    from unittest.mock import MagicMock, patch
    from rich.console import Console

    mock_pkg = MagicMock()
    m1 = MagicMock()
    m1.model = "qwen3:8b"
    mock_pkg.list.return_value = MagicMock(models=[m1])
    monkeypatch.setitem(sys.modules, "ollama", mock_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)

    from bb.ai.chat import ChatEngine, _handle_slash
    from bb.config import BBConfig
    engine = ChatEngine(BBConfig())

    # Success path
    buf = StringIO()
    con = Console(file=buf, highlight=False)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = _handle_slash("/sync", engine, con)
    assert result is False
    assert "✔" in buf.getvalue() or "Sync complete" in buf.getvalue()

    # Failure path
    buf2 = StringIO()
    con2 = Console(file=buf2, highlight=False)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        _handle_slash("/sync", engine, con2)
    assert "Sync failed" in buf2.getvalue() or "⚠" in buf2.getvalue()


# ---------------------------------------------------------------------------
# Chat history persistence
# ---------------------------------------------------------------------------

def test_history_saved_after_turn(monkeypatch, tmp_path):
    """After a successful turn, user+assistant pair is saved to chat_history.json."""
    import sys
    monkeypatch.setattr("bb.config.BB_DIR", tmp_path)
    monkeypatch.setattr("bb.ai.chat._config_module.BB_DIR", tmp_path)

    mock_pkg = _make_mock_ollama_module(response_text="Here are your deadlines.")
    monkeypatch.setitem(sys.modules, "ollama", mock_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)

    from bb.ai.chat import ChatEngine
    from bb.config import BBConfig
    engine = ChatEngine(BBConfig())
    engine.process_turn("what are my deadlines?")

    history_file = tmp_path / "chat_history.json"
    assert history_file.exists()
    history = json.loads(history_file.read_text())
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "what are my deadlines?"}
    assert history[1] == {"role": "assistant", "content": "Here are your deadlines."}


def test_history_loaded_on_init(monkeypatch, tmp_path):
    """ChatEngine loads saved history into _msgs on __init__."""
    import sys
    monkeypatch.setattr("bb.config.BB_DIR", tmp_path)
    monkeypatch.setattr("bb.ai.chat._config_module.BB_DIR", tmp_path)

    # Pre-populate history file
    history = [
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer"},
    ]
    (tmp_path / "chat_history.json").write_text(json.dumps(history))

    mock_pkg = _make_mock_ollama_module()
    monkeypatch.setitem(sys.modules, "ollama", mock_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)

    from bb.ai.chat import ChatEngine
    from bb.config import BBConfig
    engine = ChatEngine(BBConfig())

    # system + 2 history messages
    assert len(engine._msgs) == 3
    assert engine._msgs[1] == {"role": "user", "content": "old question"}
    assert engine._msgs[2] == {"role": "assistant", "content": "old answer"}


def test_history_missing_file_starts_fresh(monkeypatch, tmp_path):
    """Missing history file → fresh start, no error."""
    import sys
    monkeypatch.setattr("bb.config.BB_DIR", tmp_path)
    monkeypatch.setattr("bb.ai.chat._config_module.BB_DIR", tmp_path)

    mock_pkg = _make_mock_ollama_module()
    monkeypatch.setitem(sys.modules, "ollama", mock_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)

    from bb.ai.chat import ChatEngine
    from bb.config import BBConfig
    engine = ChatEngine(BBConfig())
    assert len(engine._msgs) == 1  # only system prompt
    assert engine._msgs[0]["role"] == "system"


def test_history_corrupted_file_starts_fresh(monkeypatch, tmp_path):
    """Corrupted history file → fresh start, no crash."""
    import sys
    monkeypatch.setattr("bb.config.BB_DIR", tmp_path)
    monkeypatch.setattr("bb.ai.chat._config_module.BB_DIR", tmp_path)

    (tmp_path / "chat_history.json").write_text("not valid json {{{{")

    mock_pkg = _make_mock_ollama_module()
    monkeypatch.setitem(sys.modules, "ollama", mock_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)

    from bb.ai.chat import ChatEngine
    from bb.config import BBConfig
    engine = ChatEngine(BBConfig())
    assert len(engine._msgs) == 1


def test_clear_history_wipes_file(monkeypatch, tmp_path):
    """/clear resets msgs to [system] only AND wipes chat_history.json."""
    import sys
    monkeypatch.setattr("bb.config.BB_DIR", tmp_path)
    monkeypatch.setattr("bb.ai.chat._config_module.BB_DIR", tmp_path)

    # Pre-populate history
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    (tmp_path / "chat_history.json").write_text(json.dumps(history))

    mock_pkg = _make_mock_ollama_module()
    monkeypatch.setitem(sys.modules, "ollama", mock_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)

    from bb.ai.chat import ChatEngine
    from bb.config import BBConfig
    engine = ChatEngine(BBConfig())
    assert len(engine._msgs) == 3  # system + 2 history

    engine.clear_history()

    # In-memory: only system
    assert len(engine._msgs) == 1
    assert engine._msgs[0]["role"] == "system"

    # File: empty list
    saved = json.loads((tmp_path / "chat_history.json").read_text())
    assert saved == []


def test_history_trimmed_to_50_messages(monkeypatch, tmp_path):
    """History file is trimmed to last 50 messages (FIFO) on save."""
    import sys
    monkeypatch.setattr("bb.config.BB_DIR", tmp_path)
    monkeypatch.setattr("bb.ai.chat._config_module.BB_DIR", tmp_path)

    # Pre-populate with 50 messages (25 pairs)
    history = []
    for i in range(25):
        history.append({"role": "user", "content": f"q{i}"})
        history.append({"role": "assistant", "content": f"a{i}"})
    (tmp_path / "chat_history.json").write_text(json.dumps(history))

    mock_pkg = _make_mock_ollama_module(response_text="new answer")
    monkeypatch.setitem(sys.modules, "ollama", mock_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)

    from bb.ai.chat import ChatEngine
    from bb.config import BBConfig
    engine = ChatEngine(BBConfig())
    engine.process_turn("new question")

    saved = json.loads((tmp_path / "chat_history.json").read_text())
    assert len(saved) == 50  # trimmed to max
    # Oldest pair (q0/a0) should have been dropped
    assert saved[0]["content"] != "q0"
    # Newest pair should be last
    assert saved[-1] == {"role": "assistant", "content": "new answer"}
