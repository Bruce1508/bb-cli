"""
Tests for `bb due` command in bb/cli.py

Strategy:
- Seed a real SQLite DB at tmp_path/bb.db
- Patch bb.config.BB_DIR → tmp_path so bb due uses the seeded DB
- Invoke via typer.testing.CliRunner

Success criteria:
- Empty DB → "No upcoming deadlines in the next N days."
- Non-empty DB → Rich table with Course and Assignment columns
- --days N → only shows deadlines within N days from now
- --course CODE → filters case-insensitively
- --json → valid JSON array with required fields
- --all → includes deadlines from up to 1 day in the past
- Always exits with code 0
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from bb.adapters.base import Deadline
from bb.cli import app
from bb.db import Database

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_deadline(
    id: str,
    course: str,
    title: str,
    days_from_now: float,
    source: str = "ical",
) -> Deadline:
    due = datetime.now(timezone.utc) + timedelta(days=days_from_now)
    return Deadline(id=id, course=course, title=title, due_at=due, source=source)


def _seed(tmp_path, *deadlines: Deadline) -> None:
    """Write deadlines into a fresh DB at tmp_path/bb.db."""
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        for d in deadlines:
            db.upsert_deadline(d)


def _invoke_due(tmp_path, *extra_args: str):
    with patch("bb.config.BB_DIR", tmp_path):
        return runner.invoke(app, ["due", *extra_args])


# ---------------------------------------------------------------------------
# Exit code
# ---------------------------------------------------------------------------


def test_due_exits_with_zero_on_empty_db(tmp_path):
    result = _invoke_due(tmp_path)
    assert result.exit_code == 0, result.output


def test_due_exits_with_zero_with_data(tmp_path):
    _seed(tmp_path, _make_deadline("dl-1", "BTI325", "Lab 5", days_from_now=3))
    result = _invoke_due(tmp_path)
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------


def test_due_empty_db_shows_no_deadlines_message(tmp_path):
    result = _invoke_due(tmp_path)
    assert "No upcoming deadlines" in result.output


def test_due_empty_db_message_includes_day_count(tmp_path):
    result = _invoke_due(tmp_path, "--days", "14")
    assert "14" in result.output


def test_due_no_table_rendered_when_empty(tmp_path):
    result = _invoke_due(tmp_path)
    assert "Course" not in result.output


# ---------------------------------------------------------------------------
# Table content
# ---------------------------------------------------------------------------


def test_due_shows_course_in_output(tmp_path):
    _seed(tmp_path, _make_deadline("dl-1", "BTI325", "Lab 5", days_from_now=3))
    result = _invoke_due(tmp_path)
    assert "BTI325" in result.output


def test_due_shows_title_in_output(tmp_path):
    _seed(tmp_path, _make_deadline("dl-1", "BTI325", "Lab 5", days_from_now=3))
    result = _invoke_due(tmp_path)
    assert "Lab 5" in result.output


def test_due_shows_multiple_deadlines(tmp_path):
    _seed(
        tmp_path,
        _make_deadline("dl-1", "BTI325", "Lab 5", days_from_now=2),
        _make_deadline("dl-2", "OOP244", "Workshop 7", days_from_now=5),
    )
    result = _invoke_due(tmp_path)
    assert "BTI325" in result.output
    assert "OOP244" in result.output


# ---------------------------------------------------------------------------
# --days flag
# ---------------------------------------------------------------------------


def test_due_days_flag_excludes_deadline_beyond_window(tmp_path):
    _seed(tmp_path, _make_deadline("dl-far", "BTI325", "Lab 5", days_from_now=10))
    result = _invoke_due(tmp_path, "--days", "7")
    assert "Lab 5" not in result.output


def test_due_days_flag_includes_deadline_within_window(tmp_path):
    _seed(tmp_path, _make_deadline("dl-near", "BTI325", "Lab 5", days_from_now=5))
    result = _invoke_due(tmp_path, "--days", "7")
    assert "Lab 5" in result.output


def test_due_default_window_is_7_days(tmp_path):
    _seed(tmp_path, _make_deadline("dl-8", "BTI325", "Lab 5", days_from_now=8))
    result = _invoke_due(tmp_path)  # default --days 7
    assert "No upcoming deadlines" in result.output


# ---------------------------------------------------------------------------
# --course filter
# ---------------------------------------------------------------------------


def test_due_course_filter_shows_matching_course(tmp_path):
    _seed(
        tmp_path,
        _make_deadline("dl-1", "BTI325", "Lab 5", days_from_now=3),
        _make_deadline("dl-2", "OOP244", "Workshop 7", days_from_now=3),
    )
    result = _invoke_due(tmp_path, "--course", "BTI325")
    assert "BTI325" in result.output


def test_due_course_filter_hides_other_courses(tmp_path):
    _seed(
        tmp_path,
        _make_deadline("dl-1", "BTI325", "Lab 5", days_from_now=3),
        _make_deadline("dl-2", "OOP244", "Workshop 7", days_from_now=3),
    )
    result = _invoke_due(tmp_path, "--course", "BTI325")
    assert "OOP244" not in result.output


def test_due_course_filter_case_insensitive(tmp_path):
    _seed(tmp_path, _make_deadline("dl-1", "BTI325", "Lab 5", days_from_now=3))
    result = _invoke_due(tmp_path, "--course", "bti325")
    assert "BTI325" in result.output


def test_due_course_filter_no_match_shows_empty_message(tmp_path):
    _seed(tmp_path, _make_deadline("dl-1", "BTI325", "Lab 5", days_from_now=3))
    result = _invoke_due(tmp_path, "--course", "ZZZ999")
    assert "No upcoming deadlines" in result.output


# ---------------------------------------------------------------------------
# --json flag
# ---------------------------------------------------------------------------


def test_due_json_flag_outputs_valid_json(tmp_path):
    _seed(tmp_path, _make_deadline("dl-1", "BTI325", "Lab 5", days_from_now=3))
    result = _invoke_due(tmp_path, "--json")
    data = json.loads(result.output)  # raises if invalid JSON
    assert isinstance(data, list)


def test_due_json_flag_contains_required_fields(tmp_path):
    _seed(tmp_path, _make_deadline("dl-1", "BTI325", "Lab 5", days_from_now=3))
    result = _invoke_due(tmp_path, "--json")
    data = json.loads(result.output)
    assert len(data) == 1
    item = data[0]
    assert "id" in item
    assert "course" in item
    assert "title" in item
    assert "due_at" in item
    assert "source" in item


def test_due_json_flag_correct_values(tmp_path):
    _seed(tmp_path, _make_deadline("dl-1", "BTI325", "Lab 5", days_from_now=3))
    result = _invoke_due(tmp_path, "--json")
    data = json.loads(result.output)
    item = data[0]
    assert item["id"] == "dl-1"
    assert item["course"] == "BTI325"
    assert item["title"] == "Lab 5"
    assert item["source"] == "ical"


def test_due_json_empty_db_returns_empty_array(tmp_path):
    result = _invoke_due(tmp_path, "--json")
    data = json.loads(result.output)
    assert data == []


# ---------------------------------------------------------------------------
# --all flag (includes overdue, up to 1 day back)
# ---------------------------------------------------------------------------


def test_due_all_flag_includes_recent_overdue(tmp_path):
    """--all shows deadlines from up to 1 day ago."""
    _seed(tmp_path, _make_deadline("dl-past", "BTI325", "Lab 5", days_from_now=-0.5))
    result = _invoke_due(tmp_path, "--all")
    assert "Lab 5" in result.output


def test_due_without_all_flag_excludes_past(tmp_path):
    """Without --all, past deadlines are not shown."""
    _seed(tmp_path, _make_deadline("dl-past", "BTI325", "Lab 5", days_from_now=-0.5))
    result = _invoke_due(tmp_path)
    assert "Lab 5" not in result.output
