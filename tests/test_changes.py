from datetime import datetime, timezone

from bb.adapters.base import Deadline, GradeItem
from bb.changes import Change, diff_deadline, diff_grade, humanize


def _deadline(due: str) -> Deadline:
    return Deadline(id="d1", course="BTP200", title="Lab 4",
                    due_at=datetime.fromisoformat(due), source="ical")


def test_diff_deadline_detects_moved_due_date():
    old = "2026-08-07T03:59:00+00:00"
    new = _deadline("2026-08-08T03:59:00+00:00")
    changes = diff_deadline(old, new)
    assert len(changes) == 1
    c = changes[0]
    assert c.change_type == "due_moved"
    assert c.field == "due_at"
    assert c.old_value == old
    assert c.new_value == "2026-08-08T03:59:00+00:00"
    assert c.item_type == "deadline"
    assert c.course == "BTP200"


def test_diff_deadline_no_change_returns_empty():
    same = "2026-08-07T03:59:00+00:00"
    assert diff_deadline(same, _deadline(same)) == []


def _grade(score, status) -> GradeItem:
    return GradeItem(id="g1", course="OPS445", item="Quiz 3",
                     score=score, out_of=100.0, status=status)


def test_diff_grade_posted_when_becomes_graded():
    changes = diff_grade(None, "pending", _grade(85.0, "graded"))
    assert len(changes) == 1
    assert changes[0].change_type == "grade_posted"
    assert changes[0].field == "status"


def test_diff_grade_changed_when_score_differs():
    changes = diff_grade(80.0, "graded", _grade(85.0, "graded"))
    assert len(changes) == 1
    assert changes[0].change_type == "grade_changed"
    assert changes[0].field == "score"
    assert changes[0].old_value == "80.0"
    assert changes[0].new_value == "85.0"


def test_diff_grade_no_change_returns_empty():
    assert diff_grade(85.0, "graded", _grade(85.0, "graded")) == []


def test_humanize_groups_by_course():
    now = datetime.now(timezone.utc).isoformat()
    changes = [
        Change("OPS445", "grade", "g1", "Quiz 3", "status", "grade_posted",
               "pending", "graded", now),
        Change("BTP200", "deadline", "d1", "Lab 4", "due_at", "due_moved",
               "2026-08-07T03:59:00+00:00", "2026-08-08T03:59:00+00:00", now),
    ]
    text = humanize(changes)
    assert "OPS445:" in text
    assert "BTP200:" in text
    assert "Quiz 3" in text
    assert "Lab 4" in text
    assert ";" in text  # two course groups joined
