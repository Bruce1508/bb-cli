"""Tool function registry for bb chat and MCP server.

TOOL_REGISTRY maps tool names to callable functions. Both the AI chat engine
(bb chat) and the MCP server (bb mcp-server) use this registry to discover
available tools and expose them to the LLM.
"""

from bb.tools.queries import (
    get_announcements,
    get_course_content,
    get_course_list,
    get_grades,
    get_sync_status,
    get_upcoming_deadlines,
    search_content,
)

TOOL_REGISTRY: dict[str, object] = {
    "get_upcoming_deadlines": get_upcoming_deadlines,
    "get_grades": get_grades,
    "get_announcements": get_announcements,
    "get_course_list": get_course_list,
    "get_sync_status": get_sync_status,
    "get_course_content": get_course_content,
    "search_content": search_content,
}
