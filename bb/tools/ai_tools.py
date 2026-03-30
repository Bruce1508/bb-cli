"""AI aggregator tools for bb chat.

These tools gather and combine data from multiple sources to give the main LLM
everything it needs to answer higher-level questions (study plans, summaries,
key concepts, study time estimates). They do NOT call the LLM themselves —
the main chat engine does all reasoning from the returned data.
"""

from __future__ import annotations

from bb.tools.queries import (
    get_course_content,
    get_grades,
    get_upcoming_deadlines,
    list_downloaded_files,
    read_file_content,
    search_content,
)


def summarize_content(course: str, filename: str) -> dict:
    """Retrieve text content from a downloaded course file so the LLM can summarize it.

    Use this when the student asks to summarize, explain, or get an overview of a
    specific file (e.g. 'summarize the BTP200 syllabus' or 'what does the week3 PDF say').

    Internally calls read_file_content and passes the result straight through so the
    main LLM receives the full text and does the actual summarization itself.

    Args:
        course: Course code (e.g. 'BTP200').
        filename: Exact or partial filename to look up. Case-insensitive substring match.

    Returns:
        On success: {filename, course, text, pages, char_count, truncated}
        On failure: {error: "file not found"} or {error: "not a PDF"} or
                    {error: "unreadable: <reason>"}
    """
    return read_file_content(course=course, filename=filename)


def generate_study_plan(course: str, exam_type: str | None = None) -> dict:
    """Aggregate all course data needed to generate a personalised study plan.

    Use this when the student asks for a study plan, study schedule, revision strategy,
    or 'how should I prepare for my exam in <COURSE>'.

    Collects grades, upcoming deadlines, downloaded files, and the cached content tree
    for the course, then returns everything as one dict so the main LLM can build a
    concrete, evidence-based study plan from real data.

    Args:
        course: Course code to plan for (e.g. 'BTI325').
        exam_type: Optional hint like 'midterm', 'final', 'quiz'.

    Returns:
        {course, exam_type, grades, upcoming_deadlines, available_files, content_tree}
    """
    try:
        grades = get_grades(course=course)
    except Exception:
        grades = []

    try:
        upcoming_deadlines = get_upcoming_deadlines(days=30, course=course)
    except Exception:
        upcoming_deadlines = []

    try:
        available_files = list_downloaded_files(course=course)
    except Exception:
        available_files = []

    try:
        content_tree = get_course_content(course=course)
    except Exception:
        content_tree = {}

    return {
        "course": course.upper(),
        "exam_type": exam_type,
        "grades": grades,
        "upcoming_deadlines": upcoming_deadlines,
        "available_files": available_files,
        "content_tree": content_tree,
    }


def extract_key_concepts(course: str) -> dict:
    """Gather course materials so the LLM can identify the key concepts to study.

    Use this when the student asks 'what are the key concepts in BTP200', 'what topics
    should I focus on for BTI325', or 'what is this course about'.

    Collects downloaded files and a flat inventory of all cached content items for the
    course so the LLM can infer important topics from real file names and content titles.

    Args:
        course: Course code (e.g. 'OOP244').

    Returns:
        {course, downloaded_files: list[dict], content_items: list[{title, type, url}]}
    """
    try:
        downloaded_files = list_downloaded_files(course=course)
    except Exception:
        downloaded_files = []

    try:
        raw_items = _flatten_content_tree(get_course_content(course=course))
    except Exception:
        raw_items = []

    try:
        search_results = search_content(query=course, course=course)
    except Exception:
        search_results = []

    seen: set[tuple] = set()
    content_items: list[dict] = []
    for item in raw_items + search_results:
        if not isinstance(item, dict):
            continue
        key = (item.get("title", ""), item.get("type", ""), item.get("url", ""))
        if key not in seen:
            seen.add(key)
            content_items.append({
                "title": item.get("title", ""),
                "type": item.get("type", ""),
                "url": item.get("url"),
            })

    return {
        "course": course.upper(),
        "downloaded_files": downloaded_files,
        "content_items": content_items,
    }


def estimate_study_time(course: str, target_grade: str | None = None) -> dict:
    """Gather grade and deadline data so the LLM can estimate required study time.

    Use this when the student asks 'how much time should I study for BTI325',
    'will I pass if I study X hours', or 'what grade do I need on the final'.

    Collects current grades, remaining deadlines (next 30 days), and downloaded
    files so the LLM can produce a realistic, data-grounded time estimate.

    Args:
        course: Course code (e.g. 'BTI325').
        target_grade: Optional desired grade like 'A', 'B+', '80%'.

    Returns:
        {course, target_grade, current_grades, remaining_deadlines, downloaded_files}
    """
    try:
        current_grades = get_grades(course=course)
    except Exception:
        current_grades = []

    try:
        remaining_deadlines = get_upcoming_deadlines(days=30, course=course)
    except Exception:
        remaining_deadlines = []

    try:
        downloaded_files = list_downloaded_files(course=course)
    except Exception:
        downloaded_files = []

    return {
        "course": course.upper(),
        "target_grade": target_grade,
        "current_grades": current_grades,
        "remaining_deadlines": remaining_deadlines,
        "downloaded_files": downloaded_files,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _flatten_content_tree(tree: dict) -> list[dict]:
    """Walk a content_tree_to_dict result and return a flat list of {title, type, url}."""
    results: list[dict] = []
    _walk_items(tree.get("items", []), results)
    return results


def _walk_items(items: list, results: list[dict]) -> None:
    """Recursively collect all content items from a nested tree."""
    for item in items:
        if not isinstance(item, dict):
            continue
        results.append({
            "title": item.get("title", ""),
            "type": item.get("type", ""),
            "url": item.get("url"),
        })
        children = item.get("children")
        if children:
            _walk_items(children, results)
