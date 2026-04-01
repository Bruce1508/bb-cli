"""Tests for bb/mcp/server.py — MCP registration contract."""
from __future__ import annotations

import sys
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Group 3: Import safety
# ---------------------------------------------------------------------------

def test_import_does_not_call_run():
    """Importing bb.mcp.server must NOT call mcp.run() — that would block on stdin."""
    sys.modules.pop("bb.mcp.server", None)
    with patch("mcp.server.fastmcp.FastMCP.run") as mock_run:
        import bb.mcp.server  # noqa: F401
        assert mock_run.call_count == 0
    sys.modules.pop("bb.mcp.server", None)  # clean up so other tests use fresh import


def test_run_is_callable():
    """bb.mcp.server.run must be a plain sync callable (not an async coroutine)."""
    import asyncio
    import bb.mcp.server as srv
    assert callable(srv.run)
    assert not asyncio.iscoroutinefunction(srv.run)


# ---------------------------------------------------------------------------
# Group 1: Registration correctness
# Note: FastMCP has no public get_tool() — use _tool_manager.get_tool(name).
# The returned Tool object has .description (str) and .parameters (dict),
# NOT .inputSchema — that attribute is only on mcp.types.Tool from list_tools().
# ---------------------------------------------------------------------------

def test_all_registry_tools_are_registered():
    """All 13 tools from TOOL_REGISTRY must be registered on the FastMCP instance."""
    import bb.mcp.server as srv
    from bb.tools import TOOL_REGISTRY
    assert len(TOOL_REGISTRY) == 13, f"Expected 13 tools, got {len(TOOL_REGISTRY)}"
    for name in TOOL_REGISTRY:
        tool = srv.mcp._tool_manager.get_tool(name)
        assert tool is not None, f"Tool '{name}' is missing from MCP server"


def test_each_tool_has_non_empty_description():
    """Every registered tool must have a non-empty description (read from docstring)."""
    import bb.mcp.server as srv
    from bb.tools import TOOL_REGISTRY
    for name in TOOL_REGISTRY:
        tool = srv.mcp._tool_manager.get_tool(name)
        assert tool is not None
        assert tool.description, f"Tool '{name}' has an empty description"


def test_each_tool_has_valid_parameters_schema():
    """Every registered tool must have a parameters dict with type=object."""
    import bb.mcp.server as srv
    from bb.tools import TOOL_REGISTRY
    for name in TOOL_REGISTRY:
        tool = srv.mcp._tool_manager.get_tool(name)
        assert tool is not None
        assert isinstance(tool.parameters, dict), f"Tool '{name}' missing parameters"
        assert tool.parameters.get("type") == "object", (
            f"Tool '{name}' parameters.type is not 'object'"
        )


# ---------------------------------------------------------------------------
# Group 2: Tool execution (via TOOL_REGISTRY directly)
# Note: We call TOOL_REGISTRY[name](**args) directly, NOT FastMCP.call_tool().
# FastMCP.call_tool() returns TextContent objects, not raw Python types.
# The contract we're testing here is that the underlying functions work
# correctly when accessed through the same registry the MCP server uses.
# ---------------------------------------------------------------------------

def test_get_course_list_returns_list(tmp_path, monkeypatch):
    """get_course_list() returns an empty list gracefully when no DB exists."""
    monkeypatch.setattr("bb.config.BB_DIR", tmp_path)
    monkeypatch.setattr("bb.db.BB_DIR", tmp_path)
    from bb.tools import TOOL_REGISTRY
    result = TOOL_REGISTRY["get_course_list"]()
    assert isinstance(result, list)


def test_get_course_content_missing_required_arg_raises():
    """get_course_content() with no args raises TypeError — 'course' is required."""
    import pytest
    from bb.tools import TOOL_REGISTRY
    with pytest.raises(TypeError):
        TOOL_REGISTRY["get_course_content"]()


def test_tool_isolation_failure_does_not_affect_others(tmp_path, monkeypatch):
    """One tool raising must not prevent other tools from running."""
    monkeypatch.setattr("bb.config.BB_DIR", tmp_path)
    monkeypatch.setattr("bb.db.BB_DIR", tmp_path)
    from bb.tools import TOOL_REGISTRY
    # Trigger failure on get_course_content (missing arg)
    try:
        TOOL_REGISTRY["get_course_content"]()
    except TypeError:
        pass
    # Other tools must still work
    result = TOOL_REGISTRY["get_course_list"]()
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------

def test_cli_mcp_server_command_exists():
    """bb mcp-server command must be registered in the Typer app."""
    from typer.testing import CliRunner
    from bb.cli import app
    runner = CliRunner()
    result = runner.invoke(app, ["mcp-server", "--help"])
    assert result.exit_code == 0
    assert "stdio" in result.output.lower() or "mcp" in result.output.lower()
