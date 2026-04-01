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
