"""
Tests for `bb grades` command in bb/cli.py

Strategy:
- Patch bb.config.BB_DIR → tmp_path so the command opens tmp_path/bb.db
- Seed grade rows with db.upsert_grade
- Use typer.testing.CliRunner for full CLI invocation

Success criteria:
- exits 0 always
- empty DB: prints "No grades found"
- filtered empty: prints "No grades found for <COURSE>"
- with rows: shows course, item, score/out_of, status
- --course filter: only shows matching course
- --json: outputs valid JSON array with correct keys
- NEW highlight: notified_at=None + status="graded" → item rendered bold
- already-notified: notified_at set → no bold
- status styling: graded=green, submitted=yellow, other=dim (not asserted directly — just no crash)
- score=None shows dash
"""
import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from bb.adapters.base import GradeItem
from bb.cli import app
from bb.db import Database

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_grades(tmp_path, grades: list[GradeItem]) -> None:
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        for g in grades:
            db.upsert_grade(g)


def _make_grade(
    id: str = "g-1",
    course: str = "BTI325",
    item: str = "Lab 1",
    score: float = 18.0,
    out_of: float = 20.0,
    status: str = "graded",
) -> GradeItem:
    return GradeItem(id=id, course=course, item=item, score=score, out_of=out_of, status=status)


def _invoke(tmp_path, *args):
    with patch("bb.config.BB_DIR", tmp_path):
        return runner.invoke(app, ["grades", *args])


# ---------------------------------------------------------------------------
# Exit code
# ---------------------------------------------------------------------------


def test_grades_exits_zero_on_empty_db(tmp_path):
    _seed_grades(tmp_path, [])
    result = _invoke(tmp_path)
    assert result.exit_code == 0, result.output


def test_grades_exits_zero_with_rows(tmp_path):
    _seed_grades(tmp_path, [_make_grade()])
    result = _invoke(tmp_path)
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# Empty state messages
# ---------------------------------------------------------------------------


def test_grades_shows_no_grades_when_empty(tmp_path):
    _seed_grades(tmp_path, [])
    result = _invoke(tmp_path)
    assert "No grades found" in result.output


def test_grades_shows_course_filter_in_empty_message(tmp_path):
    _seed_grades(tmp_path, [])
    result = _invoke(tmp_path, "--course", "BTI325")
    assert "BTI325" in result.output


# ---------------------------------------------------------------------------
# Row content
# ---------------------------------------------------------------------------


def test_grades_shows_course_code(tmp_path):
    _seed_grades(tmp_path, [_make_grade(course="BTI325")])
    result = _invoke(tmp_path)
    assert "BTI325" in result.output


def test_grades_shows_item_name(tmp_path):
    _seed_grades(tmp_path, [_make_grade(item="Midterm Exam")])
    result = _invoke(tmp_path)
    assert "Midterm" in result.output


def test_grades_shows_score_and_out_of(tmp_path):
    _seed_grades(tmp_path, [_make_grade(score=85.0, out_of=100.0)])
    result = _invoke(tmp_path)
    assert "85" in result.output
    assert "100" in result.output


def test_grades_shows_status(tmp_path):
    _seed_grades(tmp_path, [_make_grade(status="graded")])
    result = _invoke(tmp_path)
    assert "graded" in result.output


# ---------------------------------------------------------------------------
# --course filter
# ---------------------------------------------------------------------------


def test_grades_course_filter_shows_matching_course(tmp_path):
    _seed_grades(
        tmp_path,
        [
            _make_grade(id="g-1", course="BTI325", item="Lab 1"),
            _make_grade(id="g-2", course="BTI425", item="Project"),
        ],
    )
    result = _invoke(tmp_path, "--course", "BTI325")
    assert "BTI325" in result.output


def test_grades_course_filter_hides_other_courses(tmp_path):
    _seed_grades(
        tmp_path,
        [
            _make_grade(id="g-1", course="BTI325", item="Lab 1"),
            _make_grade(id="g-2", course="BTI425", item="Project"),
        ],
    )
    result = _invoke(tmp_path, "--course", "BTI325")
    assert "BTI425" not in result.output


def test_grades_course_filter_is_case_insensitive(tmp_path):
    _seed_grades(tmp_path, [_make_grade(course="BTI325")])
    result = _invoke(tmp_path, "--course", "bti325")
    assert "BTI325" in result.output


def test_grades_course_filter_empty_shows_no_grades_for_course(tmp_path):
    _seed_grades(tmp_path, [_make_grade(course="BTI325")])
    result = _invoke(tmp_path, "--course", "CPS530")
    assert "No grades found" in result.output


# ---------------------------------------------------------------------------
# --json output
# ---------------------------------------------------------------------------


def test_grades_json_flag_produces_valid_json(tmp_path):
    _seed_grades(tmp_path, [_make_grade()])
    result = _invoke(tmp_path, "--json")
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)


def test_grades_json_has_required_keys(tmp_path):
    _seed_grades(tmp_path, [_make_grade()])
    result = _invoke(tmp_path, "--json")
    data = json.loads(result.output)
    assert len(data) == 1
    row = data[0]
    assert "course" in row
    assert "item" in row
    assert "score" in row
    assert "out_of" in row
    assert "status" in row


def test_grades_json_empty_returns_empty_array(tmp_path):
    _seed_grades(tmp_path, [])
    result = _invoke(tmp_path, "--json")
    data = json.loads(result.output)
    assert data == []


def test_grades_json_correct_values(tmp_path):
    _seed_grades(tmp_path, [_make_grade(course="BTI325", item="Lab 1", score=18.0, out_of=20.0)])
    result = _invoke(tmp_path, "--json")
    data = json.loads(result.output)
    assert data[0]["course"] == "BTI325"
    assert data[0]["item"] == "Lab 1"
    assert data[0]["score"] == 18.0
    assert data[0]["out_of"] == 20.0


# ---------------------------------------------------------------------------
# NEW highlight (notified_at=None + status="graded")
# ---------------------------------------------------------------------------


def test_grades_new_item_shows_item_name(tmp_path):
    """An unnotified graded item must still show the item name."""
    _seed_grades(tmp_path, [_make_grade(item="Lab 1", status="graded")])
    result = _invoke(tmp_path)
    assert "Lab 1" in result.output
