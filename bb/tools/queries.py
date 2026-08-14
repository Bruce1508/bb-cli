"""Tool functions that the AI chat engine calls to get real Blackboard data.

Each function:
- Has a clear docstring written for the LLM (explains WHEN to call it)
- Accepts simple typed arguments
- Returns plain dicts (JSON-serializable, LLM-friendly)
- Handles a missing/uninitialized DB gracefully (returns empty list/dict)
"""

from __future__ import annotations

import pdfplumber

import bb.config as _config_module
from bb.db import Database


def get_upcoming_deadlines(days: int = 14, course: str | None = None) -> list[dict]:
    """Return upcoming deadlines from the local database.

    Use this tool when the student asks about homework, assignments, deadlines,
    due dates, or anything like 'what do I have coming up' or 'what's due soon'.

    Args:
        days: Number of days to look ahead (default 14, max 30).
        course: Specific course code to filter by (e.g. 'BTI325'). Omit or pass
            None to get deadlines for ALL courses. Do NOT pass 'all' — pass None.
    """
    BB_DIR = _config_module.BB_DIR
    # Normalize LLM-generated sentinel values that mean "no filter"
    if course and course.lower() in ("all", "any", "*", "none"):
        course = None
    try:
        with Database(BB_DIR / "bb.db") as db:
            db.setup()
            deadlines = db.get_upcoming_deadlines(days=days)
    except Exception:
        return []

    if course:
        deadlines = [d for d in deadlines if d.course.upper() == course.upper()]

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    result = []
    for d in deadlines:
        delta = d.due_at - now
        hours = delta.total_seconds() / 3600
        if hours < 0:
            when = f"was due {abs(int(hours))}h ago (today)"
        elif hours < 24:
            when = f"due in {int(hours)}h (today)"
        elif hours < 48:
            when = "due tomorrow"
        else:
            when = f"due in {int(hours / 24)} days"
        result.append({
            "course": d.course,
            "title": d.title,
            "due_at": d.due_at.isoformat(),
            "when": when,
            "source": d.source,
        })
    return result


def get_grades(course: str | None = None) -> list[dict]:
    """Return grade items from the local database.

    Use this tool when the student asks about grades, scores, marks, how they
    did on an assignment, or 'what are my grades' / 'how am I doing'.

    Args:
        course: Specific course code to filter by (e.g. 'BTI325'). Omit or pass
            None to get grades for ALL courses. Do NOT pass 'all' — pass None.
    """
    BB_DIR = _config_module.BB_DIR
    # Normalize LLM-generated sentinel values that mean "no filter"
    if course and course.lower() in ("all", "any", "*", "none"):
        course = None
    try:
        with Database(BB_DIR / "bb.db") as db:
            db.setup()
            query = "SELECT course, item, score, out_of, status FROM grades"
            params: list = []
            if course:
                query += " WHERE UPPER(course) = UPPER(?)"
                params.append(course)
            query += " ORDER BY course, item"
            rows = db._conn.execute(query, params).fetchall()
    except Exception:
        return []

    return [
        {
            "course": r[0],
            "item": r[1],
            "score": r[2],
            "out_of": r[3],
            "status": r[4],
        }
        for r in rows
    ]


def get_announcements(course: str | None = None, unread: bool = False) -> list[dict]:
    """Return recent announcements from the local database.

    Use this tool when the student asks about announcements, course updates,
    news, or 'what's new in my courses' / 'any announcements'.

    Args:
        course: Specific course code to filter by (e.g. 'BTI325'). Omit or pass
            None to get announcements for ALL courses. Do NOT pass 'all' — pass None.
        unread: If True, return only announcements not yet read.
    """
    BB_DIR = _config_module.BB_DIR
    # Normalize LLM-generated sentinel values that mean "no filter"
    if course and course.lower() in ("all", "any", "*", "none"):
        course = None
    try:
        with Database(BB_DIR / "bb.db") as db:
            db.setup()
            announcements = db.get_recent_announcements(limit=15)
    except Exception:
        return []

    if course:
        announcements = [a for a in announcements if a.course.upper() == course.upper()]
    if unread:
        announcements = [a for a in announcements if a.read_at is None]

    return [
        {
            "course": a.course,
            "title": a.title,
            "posted_at": a.posted_at.isoformat(),
            "read": a.read_at is not None,
        }
        for a in announcements
    ]


def get_course_list() -> list[str]:
    """Return all course codes that have any data in the database.

    Use this tool when the student asks what courses they have, or when you
    need to know which course codes are available for filtering other tools.
    """
    BB_DIR = _config_module.BB_DIR
    try:
        with Database(BB_DIR / "bb.db") as db:
            db.setup()
            rows = db._conn.execute(
                "SELECT DISTINCT course FROM deadlines "
                "UNION SELECT DISTINCT course FROM announcements "
                "UNION SELECT DISTINCT course FROM grades "
                "UNION SELECT DISTINCT course_code FROM course_map "
                "ORDER BY course"
            ).fetchall()
    except Exception:
        return []

    return [r[0] for r in rows]


def get_sync_status() -> dict:
    """Return the last sync time and database statistics.

    Use this tool when the student asks when data was last synced, how fresh
    the data is, or 'when was this last updated'.
    """
    BB_DIR = _config_module.BB_DIR
    try:
        with Database(BB_DIR / "bb.db") as db:
            db.setup()
            deadlines = db._conn.execute("SELECT COUNT(*) FROM deadlines").fetchone()[0]
            announcements = db._conn.execute("SELECT COUNT(*) FROM announcements").fetchone()[0]
            grades = db._conn.execute("SELECT COUNT(*) FROM grades").fetchone()[0]
            row = db._conn.execute("SELECT MAX(synced_at) FROM sync_log").fetchone()
            last_sync = row[0] if row and row[0] else None
    except Exception:
        return {"error": "Database not initialized. Run bb init."}

    return {
        "last_sync": last_sync,
        "deadlines": deadlines,
        "announcements": announcements,
        "grades": grades,
    }


def get_course_content(course: str) -> dict:
    """Return cached content tree for a course as a serializable dict.

    Use this to answer questions like:
    - 'what files are in BTP200?'
    - 'does BTI325 have lecture slides?'
    - 'list all materials for OOP244'

    Returns empty dict if course not cached — in that case suggest:
    'Run bb course <COURSE> to browse and cache the content first.'
    """
    from bb.cache import load_tree
    from bb.models.content import content_tree_to_dict

    tree = load_tree(course.upper())
    if tree is None:
        return {}
    return content_tree_to_dict(tree)


def search_content(query: str, course: str | None = None) -> list[dict]:
    """Search for content items matching query across all cached course trees.

    Use this when student asks:
    - 'find the syllabus'
    - 'where is the zoom link'
    - 'which course has lecture recordings'

    Simple substring match on title (case-insensitive).
    Returns list of {course, title, type, url} dicts.
    Set course= to restrict search to one course.
    """
    import json

    from bb.models.content import content_tree_from_dict

    cache_dir = _config_module.BB_DIR / "cache"  # resolved at call time, not import time
    results: list[dict] = []
    query_lower = query.lower()

    if course:
        dirs = [cache_dir / course.upper()]
    else:
        dirs = list(cache_dir.iterdir()) if cache_dir.exists() else []

    for course_dir in dirs:
        if not course_dir.is_dir():
            continue
        tree_file = course_dir / "tree.json"
        if not tree_file.exists():
            continue
        try:
            tree = content_tree_from_dict(json.loads(tree_file.read_text(encoding="utf-8")))
        except Exception:
            continue
        _search_items(tree.items, tree.course_code, query_lower, results)

    return results


def _search_items(items: list, course_code: str, query: str, results: list) -> None:
    """Recursive helper — traverse ContentItem tree collecting title matches."""
    for item in items:
        if query in item.title.lower():
            results.append(
                {
                    "course": course_code,
                    "title": item.title,
                    "type": item.type,
                    "url": item.url,
                }
            )
        if item.children:
            _search_items(item.children, course_code, query, results)


def list_downloaded_files(course: str | None = None) -> list[dict]:
    """Return files already downloaded to ~/.bb/files/.

    Use when student asks 'what files do I have?', 'show my downloaded materials',
    or before read_file_content to confirm a file exists.

    Args:
        course: Optional course code filter. Case-insensitive.
    """
    BB_DIR = _config_module.BB_DIR
    try:
        with Database(BB_DIR / "bb.db") as db:
            db.setup()
            return db.get_downloads(course=course)
    except Exception:
        return []


def read_file_content(course: str, filename: str) -> dict:
    """Extract text content from a downloaded PDF file.

    Use when student asks to summarize, explain, or quote from a specific course file.
    Returns the full text (capped at 8000 chars to fit LLM context).

    Args:
        course: Course code (e.g. 'BTP200').
        filename: Exact or partial filename. Case-insensitive substring match.

    Returns:
        {"filename", "course", "text", "pages", "char_count", "truncated"}
        {"error": "file not found"} if no match
        {"error": "not a PDF"} if file extension is not .pdf
        {"error": "unreadable: <reason>"} if pdfplumber fails
    """
    BB_DIR = _config_module.BB_DIR
    files_dir = BB_DIR / "files" / course.upper()
    if not files_dir.exists():
        return {"error": "file not found"}
    match = next(
        (f for f in files_dir.iterdir() if f.is_file() and filename.lower() in f.name.lower()),
        None,
    )
    if match is None:
        return {"error": "file not found"}
    if match.suffix.lower() != ".pdf":
        return {"error": "not a PDF"}
    try:
        with pdfplumber.open(match) as pdf:
            page_count = len(pdf.pages)
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception as e:
        return {"error": f"unreadable: {e}"}
    truncated = len(text) > 8000
    return {
        "filename": match.name,
        "course": course.upper(),
        "text": text[:8000],
        "pages": page_count,
        "char_count": len(text),
        "truncated": truncated,
    }


def get_recent_changes(days: int = 7, course: str | None = None) -> list[dict]:
    """Return what recently CHANGED on existing Blackboard items.

    Use this tool when the student asks what changed, what's new since last time,
    'did any deadline move', 'were any grades posted', or 'what happened this week'.
    This covers MODIFICATIONS to existing items (a due date moving, a grade being
    posted or changed) — not brand-new items.

    Args:
        days: How many days back to look (default 7).
        course: Course code to filter by (e.g. 'BTP200'). Omit or pass None for
            all courses. Do NOT pass 'all' — pass None.
    """
    BB_DIR = _config_module.BB_DIR
    if course and course.lower() in ("all", "any", "*", "none"):
        course = None
    try:
        with Database(BB_DIR / "bb.db") as db:
            db.setup()
            rows = db.get_changes(days=days, course=course)
    except Exception:
        return []
    return [
        {
            "course": c.course,
            "item_type": c.item_type,
            "title": c.title,
            "change_type": c.change_type,
            "old_value": c.old_value,
            "new_value": c.new_value,
            "detected_at": c.detected_at,
        }
        for c in rows
    ]
