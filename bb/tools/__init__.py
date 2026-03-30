"""Tool function registry for bb chat and MCP server.

TOOL_REGISTRY maps tool names to callable functions. Both the AI chat engine
(bb chat) and the MCP server (bb mcp-server) use this registry to discover
available tools and expose them to the LLM.
"""

from bb.tools.ai_tools import (
    estimate_study_time,
    extract_key_concepts,
    generate_study_plan,
    summarize_content,
)
from bb.tools.queries import (
    get_announcements,
    get_course_content,
    get_course_list,
    get_grades,
    get_sync_status,
    get_upcoming_deadlines,
    list_downloaded_files,
    read_file_content,
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
    "list_downloaded_files": list_downloaded_files,
    "read_file_content": read_file_content,
    "summarize_content": summarize_content,
    "generate_study_plan": generate_study_plan,
    "extract_key_concepts": extract_key_concepts,
    "estimate_study_time": estimate_study_time,
}
