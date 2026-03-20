"""Tool functions that the AI chat engine calls to get real Blackboard data.

Each function:
- Has a clear docstring written for the LLM (explains WHEN to call it)
- Accepts simple typed arguments
- Returns plain dicts (JSON-serializable, LLM-friendly)
- Handles a missing/uninitialized DB gracefully (returns empty list/dict)
"""

from __future__ import annotations

import bb.config as _config_module
from bb.db import Database


def get_upcoming_deadlines(days: int = 7, course: str | None = None) -> list[dict]:
    """Return upcoming deadlines from the local database.

    Use this tool when the student asks about homework, assignments, deadlines,
    due dates, or anything like 'what do I have coming up' or 'what's due soon'.

    Args:
        days: Number of days to look ahead (default 7, max 30).
        course: Optional course code filter (e.g. 'BTI325'). Case-insensitive.
    """
    BB_DIR = _config_module.BB_DIR
    try:
        with Database(BB_DIR / "bb.db") as db:
            db.setup()
            deadlines = db.get_upcoming_deadlines(days=days)
    except Exception:
        return []

    if course:
        deadlines = [d for d in deadlines if d.course.upper() == course.upper()]

    return [
        {
            "course": d.course,
            "title": d.title,
            "due_at": d.due_at.isoformat(),
            "source": d.source,
        }
        for d in deadlines
    ]


def get_grades(course: str | None = None) -> list[dict]:
    """Return grade items from the local database.

    Use this tool when the student asks about grades, scores, marks, how they
    did on an assignment, or 'what are my grades' / 'how am I doing'.

    Args:
        course: Optional course code filter (e.g. 'BTI325'). Case-insensitive.
    """
    BB_DIR = _config_module.BB_DIR
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
        course: Optional course code filter. Case-insensitive.
        unread: If True, return only announcements not yet read.
    """
    BB_DIR = _config_module.BB_DIR
    try:
        with Database(BB_DIR / "bb.db") as db:
            db.setup()
            announcements = db.get_recent_announcements(limit=50)
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
