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
