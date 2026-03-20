"""
Tests for bb/tools/queries.py and bb/tools/__init__.py (TOOL_REGISTRY)
Day 5/7 backfill — flagged at 0% coverage

Strategy:
- Patch bb.config.BB_DIR → tmp_path for all DB-touching tests
- Seed real SQLite data via Database helpers
- All tools must return plain dicts (JSON-serializable, no Deadline/Announcement objects)
- Missing/empty DB → graceful return (empty list or error dict), never raises

Success criteria:
- get_upcoming_deadlines: returns list of dicts with correct keys; filters by course
- get_grades: returns list of dicts; filters by course case-insensitively
- get_announcements: returns list of dicts; filters by course, by unread
- get_course_list: returns sorted list of course strings from all 3 tables
- get_sync_status: returns dict with last_sync, deadlines, announcements, grades counts
- All functions return empty list / error dict when DB is missing or not initialized
- TOOL_REGISTRY: all 5 expected tools present and callable
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from bb.adapters.base import Announcement, Deadline, GradeItem
from bb.db import Database
from bb.tools import TOOL_REGISTRY
from bb.tools.queries import (
    get_announcements,
    get_course_list,
    get_grades,
    get_sync_status,
    get_upcoming_deadlines,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "bb.db"
    with Database(path) as db:
        db.setup()
    return tmp_path  # return parent dir so BB_DIR patch works


def _deadline(id: str = "dl-1", course: str = "BTI325", days: float = 3.0) -> Deadline:
    return Deadline(
        id=id,
        course=course,
        title="Lab 1",
        due_at=datetime.now(timezone.utc) + timedelta(days=days),
        source="ical",
    )


def _announcement(
    id: str = "ann-1",
    course: str = "BTI325",
    read_at: datetime | None = None,
) -> Announcement:
    return Announcement(
        id=id,
        course=course,
        title="Lab Updated",
        body="See portal.",
        posted_at=datetime.now(timezone.utc),
        read_at=read_at,
    )


def _grade(id: str = "g-1", course: str = "BTI325") -> GradeItem:
    return GradeItem(id=id, course=course, item="Lab 1", score=18.0, out_of=20.0, status="graded")


# ---------------------------------------------------------------------------
# get_upcoming_deadlines
# ---------------------------------------------------------------------------


def test_get_upcoming_deadlines_returns_list(db_path):
    with patch("bb.config.BB_DIR", db_path):
        result = get_upcoming_deadlines()
    assert isinstance(result, list)


def test_get_upcoming_deadlines_empty_when_no_data(db_path):
    with patch("bb.config.BB_DIR", db_path):
        result = get_upcoming_deadlines()
    assert result == []


def test_get_upcoming_deadlines_returns_dicts(db_path):
    with Database(db_path / "bb.db") as db:
        db.setup()
        db.upsert_deadline(_deadline())
    with patch("bb.config.BB_DIR", db_path):
        result = get_upcoming_deadlines()
    assert len(result) == 1
    assert isinstance(result[0], dict)


def test_get_upcoming_deadlines_has_required_keys(db_path):
    with Database(db_path / "bb.db") as db:
        db.setup()
        db.upsert_deadline(_deadline())
    with patch("bb.config.BB_DIR", db_path):
        result = get_upcoming_deadlines()
    row = result[0]
    assert "course" in row
    assert "title" in row
    assert "due_at" in row
    assert "source" in row


def test_get_upcoming_deadlines_filters_by_course(db_path):
    with Database(db_path / "bb.db") as db:
        db.setup()
        db.upsert_deadline(_deadline(id="dl-1", course="BTI325"))
        db.upsert_deadline(_deadline(id="dl-2", course="BTI425"))
    with patch("bb.config.BB_DIR", db_path):
        result = get_upcoming_deadlines(course="BTI325")
    assert all(r["course"] == "BTI325" for r in result)


def test_get_upcoming_deadlines_filter_is_case_insensitive(db_path):
    with Database(db_path / "bb.db") as db:
        db.setup()
        db.upsert_deadline(_deadline(course="BTI325"))
    with patch("bb.config.BB_DIR", db_path):
        result = get_upcoming_deadlines(course="bti325")
    assert len(result) == 1


def test_get_upcoming_deadlines_returns_empty_list_when_no_db(tmp_path):
    """Missing db.db → graceful empty list, never raises."""
    with patch("bb.config.BB_DIR", tmp_path):
        result = get_upcoming_deadlines()
    assert result == []


# ---------------------------------------------------------------------------
# get_grades
# ---------------------------------------------------------------------------


def test_get_grades_returns_list(db_path):
    with patch("bb.config.BB_DIR", db_path):
        result = get_grades()
    assert isinstance(result, list)


def test_get_grades_empty_when_no_data(db_path):
    with patch("bb.config.BB_DIR", db_path):
        result = get_grades()
    assert result == []


def test_get_grades_returns_dicts(db_path):
    with Database(db_path / "bb.db") as db:
        db.setup()
        db.upsert_grade(_grade())
    with patch("bb.config.BB_DIR", db_path):
        result = get_grades()
    assert len(result) == 1
    assert isinstance(result[0], dict)


def test_get_grades_has_required_keys(db_path):
    with Database(db_path / "bb.db") as db:
        db.setup()
        db.upsert_grade(_grade())
    with patch("bb.config.BB_DIR", db_path):
        result = get_grades()
    row = result[0]
    assert "course" in row
    assert "item" in row
    assert "score" in row
    assert "out_of" in row
    assert "status" in row


def test_get_grades_filters_by_course(db_path):
    with Database(db_path / "bb.db") as db:
        db.setup()
        db.upsert_grade(_grade(id="g-1", course="BTI325"))
        db.upsert_grade(_grade(id="g-2", course="BTI425"))
    with patch("bb.config.BB_DIR", db_path):
        result = get_grades(course="BTI325")
    assert all(r["course"] == "BTI325" for r in result)


def test_get_grades_filter_case_insensitive(db_path):
    with Database(db_path / "bb.db") as db:
        db.setup()
        db.upsert_grade(_grade(course="BTI325"))
    with patch("bb.config.BB_DIR", db_path):
        result = get_grades(course="bti325")
    assert len(result) == 1


def test_get_grades_returns_empty_list_when_no_db(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        result = get_grades()
    assert result == []


# ---------------------------------------------------------------------------
# get_announcements
# ---------------------------------------------------------------------------


def test_get_announcements_returns_list(db_path):
    with patch("bb.config.BB_DIR", db_path):
        result = get_announcements()
    assert isinstance(result, list)


def test_get_announcements_empty_when_no_data(db_path):
    with patch("bb.config.BB_DIR", db_path):
        result = get_announcements()
    assert result == []


def test_get_announcements_returns_dicts(db_path):
    with Database(db_path / "bb.db") as db:
        db.setup()
        db.upsert_announcement(_announcement())
    with patch("bb.config.BB_DIR", db_path):
        result = get_announcements()
    assert len(result) == 1
    assert isinstance(result[0], dict)


def test_get_announcements_has_required_keys(db_path):
    with Database(db_path / "bb.db") as db:
        db.setup()
        db.upsert_announcement(_announcement())
    with patch("bb.config.BB_DIR", db_path):
        result = get_announcements()
    row = result[0]
    assert "course" in row
    assert "title" in row
    assert "posted_at" in row
    assert "read" in row


def test_get_announcements_filters_by_course(db_path):
    with Database(db_path / "bb.db") as db:
        db.setup()
        db.upsert_announcement(_announcement(id="a-1", course="BTI325"))
        db.upsert_announcement(_announcement(id="a-2", course="BTI425"))
    with patch("bb.config.BB_DIR", db_path):
        result = get_announcements(course="BTI325")
    assert all(r["course"] == "BTI325" for r in result)


def test_get_announcements_unread_filter(db_path):
    now = datetime.now(timezone.utc)
    with Database(db_path / "bb.db") as db:
        db.setup()
        db.upsert_announcement(_announcement(id="a-1", read_at=None))
        db.upsert_announcement(_announcement(id="a-2", read_at=now))
    with patch("bb.config.BB_DIR", db_path):
        result = get_announcements(unread=True)
    assert all(r["read"] is False for r in result)


def test_get_announcements_read_field_true_when_read(db_path):
    now = datetime.now(timezone.utc)
    with Database(db_path / "bb.db") as db:
        db.setup()
        db.upsert_announcement(_announcement(id="a-1", read_at=now))
    with patch("bb.config.BB_DIR", db_path):
        result = get_announcements()
    assert result[0]["read"] is True


def test_get_announcements_returns_empty_list_when_no_db(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        result = get_announcements()
    assert result == []


# ---------------------------------------------------------------------------
# get_course_list
# ---------------------------------------------------------------------------


def test_get_course_list_returns_list(db_path):
    with patch("bb.config.BB_DIR", db_path):
        result = get_course_list()
    assert isinstance(result, list)


def test_get_course_list_empty_when_no_data(db_path):
    with patch("bb.config.BB_DIR", db_path):
        result = get_course_list()
    assert result == []


def test_get_course_list_includes_course_from_deadlines(db_path):
    with Database(db_path / "bb.db") as db:
        db.setup()
        db.upsert_deadline(_deadline(course="BTI325"))
    with patch("bb.config.BB_DIR", db_path):
        result = get_course_list()
    assert "BTI325" in result


def test_get_course_list_includes_course_from_grades(db_path):
    with Database(db_path / "bb.db") as db:
        db.setup()
        db.upsert_grade(_grade(course="BTI425"))
    with patch("bb.config.BB_DIR", db_path):
        result = get_course_list()
    assert "BTI425" in result


def test_get_course_list_includes_course_from_announcements(db_path):
    with Database(db_path / "bb.db") as db:
        db.setup()
        db.upsert_announcement(_announcement(course="CPS530"))
    with patch("bb.config.BB_DIR", db_path):
        result = get_course_list()
    assert "CPS530" in result


def test_get_course_list_deduplicates(db_path):
    with Database(db_path / "bb.db") as db:
        db.setup()
        db.upsert_deadline(_deadline(id="dl-1", course="BTI325"))
        db.upsert_announcement(_announcement(id="a-1", course="BTI325"))
    with patch("bb.config.BB_DIR", db_path):
        result = get_course_list()
    assert result.count("BTI325") == 1


def test_get_course_list_returns_strings(db_path):
    with Database(db_path / "bb.db") as db:
        db.setup()
        db.upsert_deadline(_deadline(course="BTI325"))
    with patch("bb.config.BB_DIR", db_path):
        result = get_course_list()
    assert all(isinstance(c, str) for c in result)


def test_get_course_list_returns_empty_list_when_no_db(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        result = get_course_list()
    assert result == []


# ---------------------------------------------------------------------------
# get_sync_status
# ---------------------------------------------------------------------------


def test_get_sync_status_returns_dict(db_path):
    with patch("bb.config.BB_DIR", db_path):
        result = get_sync_status()
    assert isinstance(result, dict)


def test_get_sync_status_has_required_keys(db_path):
    with patch("bb.config.BB_DIR", db_path):
        result = get_sync_status()
    assert "deadlines" in result
    assert "announcements" in result
    assert "grades" in result
    assert "last_sync" in result


def test_get_sync_status_counts_are_zero_on_empty_db(db_path):
    with patch("bb.config.BB_DIR", db_path):
        result = get_sync_status()
    assert result["deadlines"] == 0
    assert result["announcements"] == 0
    assert result["grades"] == 0


def test_get_sync_status_counts_correct_rows(db_path):
    with Database(db_path / "bb.db") as db:
        db.setup()
        db.upsert_deadline(_deadline(id="dl-1"))
        db.upsert_deadline(_deadline(id="dl-2"))
        db.upsert_announcement(_announcement())
    with patch("bb.config.BB_DIR", db_path):
        result = get_sync_status()
    assert result["deadlines"] == 2
    assert result["announcements"] == 1
    assert result["grades"] == 0


def test_get_sync_status_last_sync_none_when_no_log(db_path):
    with patch("bb.config.BB_DIR", db_path):
        result = get_sync_status()
    assert result["last_sync"] is None


def test_get_sync_status_does_not_raise_when_no_db(tmp_path):
    """Missing db file → db.setup() creates it; function returns zero counts, never raises."""
    with patch("bb.config.BB_DIR", tmp_path):
        result = get_sync_status()
    assert isinstance(result, dict)
    # Either a valid status dict or an error dict — must not raise
    assert "deadlines" in result or "error" in result


# ---------------------------------------------------------------------------
# TOOL_REGISTRY
# ---------------------------------------------------------------------------


def test_tool_registry_is_dict():
    assert isinstance(TOOL_REGISTRY, dict)


def test_tool_registry_has_get_upcoming_deadlines():
    assert "get_upcoming_deadlines" in TOOL_REGISTRY


def test_tool_registry_has_get_grades():
    assert "get_grades" in TOOL_REGISTRY


def test_tool_registry_has_get_announcements():
    assert "get_announcements" in TOOL_REGISTRY


def test_tool_registry_has_get_course_list():
    assert "get_course_list" in TOOL_REGISTRY


def test_tool_registry_has_get_sync_status():
    assert "get_sync_status" in TOOL_REGISTRY


def test_tool_registry_entries_are_callable():
    for name, fn in TOOL_REGISTRY.items():
        assert callable(fn), f"{name} should be callable"


def test_tool_registry_get_upcoming_deadlines_is_correct_function():
    assert TOOL_REGISTRY["get_upcoming_deadlines"] is get_upcoming_deadlines


def test_tool_registry_get_grades_is_correct_function():
    assert TOOL_REGISTRY["get_grades"] is get_grades
