"""Tests for bb chat AI layer."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


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


def _done(*a, **kw):
    import subprocess
    return subprocess.CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")


def test_dispatch_tool_coerces_string_bool(tmp_path, monkeypatch):
    """{"full": "false"} from the LLM must mean a FAST sync, not a truthy full one."""
    monkeypatch.setattr("bb.config.BB_DIR", tmp_path)
    from bb.ai.chat import dispatch_tool
    with patch("bb.tools.actions.subprocess.run", side_effect=_done) as run:
        dispatch_tool("sync_now", {"full": "false"})
    assert "--ical-only" in run.call_args.args[0]


def test_dispatch_tool_coerces_string_int(tmp_path, monkeypatch):
    monkeypatch.setattr("bb.config.BB_DIR", tmp_path)
    (tmp_path / "files" / "X").mkdir(parents=True)
    (tmp_path / "files" / "X" / "f.pdf").touch()
    page = MagicMock()
    page.extract_text.return_value = "a" * 9000
    pdf = MagicMock(pages=[page])
    pdf.__enter__ = lambda s: s
    from bb.ai.chat import dispatch_tool
    with patch("bb.tools.queries.pdfplumber.open", return_value=pdf):
        parsed = json.loads(dispatch_tool(
            "read_file_content", {"course": "X", "filename": "f", "offset": "8000"}))
    assert parsed["offset"] == 8000 and parsed["text"] == "a" * 1000


def test_dispatch_tool_rejects_bad_types(tmp_path, monkeypatch):
    monkeypatch.setattr("bb.config.BB_DIR", tmp_path)
    from bb.ai.chat import dispatch_tool
    with patch("bb.tools.actions.subprocess.run", side_effect=_done) as run:
        parsed = json.loads(dispatch_tool("sync_now", {"full": "banana"}))
    assert "error" in parsed
    run.assert_not_called()


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
    """process_turn calls _stream_answer and returns '' sentinel when no tool calls."""
    import sys
    from unittest.mock import MagicMock, patch
    from bb.config import BBConfig

    mock_msg = MagicMock()
    mock_msg.content = "You have 3 upcoming deadlines."
    mock_msg.tool_calls = None

    mock_ollama_pkg = MagicMock()
    m1 = MagicMock()
    m1.model = "qwen3:8b"
    mock_ollama_pkg.list.return_value = MagicMock(models=[m1])
    mock_ollama_pkg.chat.return_value = MagicMock(message=mock_msg)

    monkeypatch.setitem(sys.modules, "ollama", mock_ollama_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)

    from bb.ai.chat import ChatEngine
    engine = ChatEngine(BBConfig())
    with patch.object(engine, "_stream_answer", return_value="You have 3 upcoming deadlines."):
        result = engine.process_turn("what are my deadlines?")
    # Streaming path: answer is rendered live; process_turn returns "" sentinel
    assert result == ""


def test_ollama_turn_tool_call_dispatched(monkeypatch):
    """process_turn executes tool calls then calls _stream_answer for the final response."""
    import sys
    from unittest.mock import MagicMock, patch
    from bb.config import BBConfig

    # First response: has a tool call
    tc = MagicMock()
    tc.function.name = "get_course_list"
    tc.function.arguments = {}

    msg_with_tool = MagicMock()
    msg_with_tool.content = ""
    msg_with_tool.tool_calls = [tc]

    # Second response: plain text after tool result injected → triggers _stream_answer
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
    with patch.object(engine, "_stream_answer", return_value="Your courses are: BTP200, OPS445."):
        result = engine.process_turn("list my courses")

    assert result == ""  # streaming sentinel
    assert mock_ollama_pkg.chat.call_count == 2
    # A tool result message should be in history
    roles = [m["role"] for m in engine._msgs]
    assert "tool" in roles


# ---------------------------------------------------------------------------
# run_chat() — single-shot and no-provider paths
# ---------------------------------------------------------------------------

def _make_mock_ollama_module(model: str = "qwen3:8b", response_text: str = "answer"):
    """Return a mock ollama module that handles both streaming and non-streaming calls.

    Non-streaming call (tools=..., no stream kwarg): returns a response with .message.
    Streaming call (stream=True): returns an iterator of one chunk with the response text.
    """
    from unittest.mock import MagicMock

    mock_msg = MagicMock()
    mock_msg.content = response_text
    mock_msg.tool_calls = None

    m1 = MagicMock()
    m1.model = model
    mock_pkg = MagicMock()
    mock_pkg.list.return_value = MagicMock(models=[m1])

    chunk = MagicMock()
    chunk.message.content = response_text

    def chat_side_effect(*args, **kwargs):
        if kwargs.get("stream"):
            return iter([chunk])
        return MagicMock(message=mock_msg)

    mock_pkg.chat.side_effect = chat_side_effect
    return mock_pkg


def test_run_chat_single_shot_prints_response(monkeypatch):
    """Single-shot mode streams the LLM response to console via _stream_answer."""
    import sys
    from io import StringIO
    from unittest.mock import patch
    from rich.console import Console
    mock_pkg = _make_mock_ollama_module(response_text="3 deadlines coming up.")
    monkeypatch.setitem(sys.modules, "ollama", mock_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)

    buf = StringIO()
    con = Console(file=buf, highlight=False)

    def fake_stream(_self, _con, _ollama, think):
        # Simulate streaming writing directly to console (as the real method does)
        _con.print("bb: 3 deadlines coming up.")
        return ""

    from bb.ai.chat import run_chat, ChatEngine
    from bb.config import BBConfig
    with patch.object(ChatEngine, "_stream_answer", fake_stream):
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


def test_system_prompt_does_not_hardcode_no_think():
    """Regression: /no_think must not live in the prompt — it overrides the API toggle."""
    from bb.ai.prompts import SYSTEM_PROMPT
    assert "/no_think" not in SYSTEM_PROMPT


def test_ollama_chat_receives_think_true_when_toggled(monkeypatch):
    """Regression: cfg.ai.think=True propagates to the Ollama API call."""
    import sys
    from unittest.mock import MagicMock, patch
    from bb.config import BBConfig

    msg = MagicMock()
    msg.content = "ok"
    msg.tool_calls = None

    mock_pkg = MagicMock()
    m1 = MagicMock()
    m1.model = "qwen3:8b"
    mock_pkg.list.return_value = MagicMock(models=[m1])
    mock_pkg.chat.return_value = MagicMock(message=msg)

    monkeypatch.setitem(sys.modules, "ollama", mock_pkg)
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)

    from bb.ai.chat import ChatEngine
    cfg = BBConfig()
    cfg.ai.think = True
    engine = ChatEngine(cfg)
    with patch.object(engine, "_stream_answer", return_value="ok"):
        engine.process_turn("hello")

    _, kwargs = mock_pkg.chat.call_args_list[0]
    assert kwargs.get("think") is True


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


def test_handle_slash_sync_reports_a_skip(tmp_path, monkeypatch):
    from io import StringIO

    from rich.console import Console

    from bb.ai.chat import _handle_slash
    monkeypatch.setattr("bb.config.BB_DIR", tmp_path)
    buf = StringIO()
    with patch("bb.tools.actions.sync_now",
               return_value={"ok": False, "skipped": True, "full": False, "output": ""}):
        _handle_slash("/sync", MagicMock(), Console(file=buf))
    assert "⏸ Sync skipped — another sync is running." in buf.getvalue()
    assert "failed" not in buf.getvalue()


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
    engine = ChatEngine(BBConfig(), resume=True)

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
    engine = ChatEngine(BBConfig(), resume=True)
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


def test_no_provider_help_never_suggests_unsupported_provider(monkeypatch, tmp_path):
    """Following the help text must not produce a config that load_config() rejects."""
    import io

    from rich.console import Console

    monkeypatch.setattr("bb.config.BB_DIR", tmp_path)
    monkeypatch.setattr("bb.ai.providers.ollama.is_available", lambda: False)
    from bb.ai.chat import run_chat
    from bb.config import BBConfig

    buf = io.StringIO()
    run_chat(query="hi", cfg=BBConfig(), console=Console(file=buf, width=200))
    out = buf.getvalue()
    assert "ollama pull" in out
    assert 'provider = "claude"' not in out
    assert "api_key" not in out


def test_every_tool_has_a_label():
    from bb.ai.chat import _TOOL_LABELS
    from bb.tools import TOOL_REGISTRY
    assert set(TOOL_REGISTRY) <= set(_TOOL_LABELS)


def test_estimate_study_time_does_not_promise_final_exam_math():
    from bb.ai.chat import _tool_description
    from bb.tools.ai_tools import estimate_study_time
    desc = _tool_description(estimate_study_time)
    assert "need on the final" not in desc
    assert "weights are NOT available" in desc


def test_system_prompt_forbids_grade_weight_math():
    from bb.ai.prompts import SYSTEM_PROMPT
    assert "weights are unknown" in SYSTEM_PROMPT


def test_new_session_does_not_load_old_history(monkeypatch, tmp_path):
    import sys
    monkeypatch.setattr("bb.config.BB_DIR", tmp_path)
    monkeypatch.setattr("bb.ai.chat._config_module.BB_DIR", tmp_path)
    (tmp_path / "chat_history.json").write_text(
        json.dumps([{"role": "user", "content": "old"}, {"role": "assistant", "content": "a"}])
    )
    monkeypatch.setitem(sys.modules, "ollama", _make_mock_ollama_module())
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)
    from bb.ai.chat import ChatEngine
    from bb.config import BBConfig
    engine = ChatEngine(BBConfig())
    assert len(engine._msgs) == 1
    assert engine.resume_history() == 2
    assert engine._msgs[1]["content"] == "old"


def _resume_engine(monkeypatch, tmp_path, prepopulate=True):
    import sys
    monkeypatch.setattr("bb.config.BB_DIR", tmp_path)
    monkeypatch.setattr("bb.ai.chat._config_module.BB_DIR", tmp_path)
    if prepopulate:
        (tmp_path / "chat_history.json").write_text(
            json.dumps([{"role": "user", "content": "old"}, {"role": "assistant", "content": "olda"}])
        )
    monkeypatch.setitem(sys.modules, "ollama", _make_mock_ollama_module())
    monkeypatch.delitem(sys.modules, "bb.ai.providers.ollama", raising=False)
    from bb.ai.chat import ChatEngine
    from bb.config import BBConfig
    return ChatEngine(BBConfig())


def test_resume_after_turn_does_not_duplicate(monkeypatch, tmp_path):
    engine = _resume_engine(monkeypatch, tmp_path)
    engine._msgs += [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    engine._save_history("q", "a")
    assert engine.resume_history() == 2
    assert [m["content"] for m in engine._msgs[1:]] == ["old", "olda", "q", "a"]


def test_resume_twice_is_noop(monkeypatch, tmp_path):
    engine = _resume_engine(monkeypatch, tmp_path)
    assert engine.resume_history() == 2
    n = len(engine._msgs)
    assert engine.resume_history() == 0
    assert len(engine._msgs) == n


def test_resume_after_clear_returns_zero(monkeypatch, tmp_path):
    engine = _resume_engine(monkeypatch, tmp_path)
    engine.clear_history()
    assert engine.resume_history() == 0
    assert len(engine._msgs) == 1


def test_slash_resume_without_history_says_so(monkeypatch, tmp_path):
    import io

    from rich.console import Console

    from bb.ai.chat import _handle_slash
    engine = _resume_engine(monkeypatch, tmp_path, prepopulate=False)
    buf = io.StringIO()
    _handle_slash("/resume", engine, Console(file=buf, width=200))
    assert "No earlier conversation found." in buf.getvalue()


def test_slash_sync_uses_sync_now():
    import io
    from unittest.mock import MagicMock, patch

    from rich.console import Console

    from bb.ai.chat import _handle_slash
    con = Console(file=io.StringIO())
    fake = {"ok": True, "full": False, "output": "✔ 3 deadlines (1 new)", "recent_changes": []}
    with patch("bb.tools.actions.sync_now", return_value=fake) as s:
        _handle_slash("/sync", MagicMock(), con)
        _handle_slash("/sync full", MagicMock(), con)
    assert [c.kwargs["full"] for c in s.call_args_list] == [False, True]
    assert "3 deadlines" in con.file.getvalue()
