from datetime import datetime, timezone

from bb.changes import Change
from bb.db import Database


def _db(tmp_path):
    db = Database(tmp_path / "bb.db")
    db.setup()
    return db


def _change(course="BTP200", ctype="due_moved", field="due_at") -> Change:
    return Change(course=course, item_type="deadline", item_id="d1", title="Lab 4",
                  field=field, change_type=ctype, old_value="a", new_value="b",
                  detected_at=datetime.now(timezone.utc).isoformat())


def test_record_and_get_changes(tmp_path):
    db = _db(tmp_path)
    db._record_change(_change())
    db._conn.commit()
    changes = db.get_changes()
    assert len(changes) == 1
    assert changes[0].change_type == "due_moved"
    assert changes[0].id is not None


def test_get_changes_filters_by_course(tmp_path):
    db = _db(tmp_path)
    db._record_change(_change(course="BTP200"))
    db._record_change(_change(course="OPS445"))
    db._conn.commit()
    assert len(db.get_changes(course="ops445")) == 1


def test_unacknowledged_and_acknowledge(tmp_path):
    db = _db(tmp_path)
    db._record_change(_change())
    db._conn.commit()
    unseen = db.get_changes(unacknowledged_only=True)
    assert len(unseen) == 1
    db.acknowledge_changes([unseen[0].id])
    assert db.get_changes(unacknowledged_only=True) == []


from bb.adapters.base import Deadline, GradeItem


def _deadline(due: str) -> Deadline:
    return Deadline(id="dd", course="BTP200", title="Lab 4",
                    due_at=datetime.fromisoformat(due), source="ical")


def test_upsert_deadline_records_change_on_move(tmp_path):
    db = _db(tmp_path)
    db.upsert_deadline(_deadline("2026-08-07T03:59:00+00:00"))
    db.upsert_deadline(_deadline("2026-08-08T03:59:00+00:00"))
    changes = db.get_changes()
    assert len(changes) == 1
    assert changes[0].change_type == "due_moved"


def test_upsert_deadline_no_change_records_nothing(tmp_path):
    db = _db(tmp_path)
    same = "2026-08-07T03:59:00+00:00"
    db.upsert_deadline(_deadline(same))
    db.upsert_deadline(_deadline(same))
    assert db.get_changes() == []


def test_upsert_grade_records_grade_posted(tmp_path):
    db = _db(tmp_path)
    db.upsert_grade(GradeItem(id="gg", course="OPS445", item="Quiz 3",
                              score=None, out_of=100.0, status="pending"))
    db.upsert_grade(GradeItem(id="gg", course="OPS445", item="Quiz 3",
                              score=85.0, out_of=100.0, status="graded"))
    changes = db.get_changes()
    assert len(changes) == 1
    assert changes[0].change_type == "grade_posted"
