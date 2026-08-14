import sqlite3
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

from bb.db import Database


def make_db() -> Database:
    """Helper: in-memory database, set up and ready."""
    db = Database(":memory:")
    db.setup()
    return db


def test_setup_completes_without_error():
    db = Database(":memory:")
    db.setup()  # must not raise
    db.close()


def test_schema_version_is_1_after_setup():
    with make_db() as db:
        row = db._conn.execute("SELECT version FROM schema_version").fetchone()
        assert row[0] == 1


def test_setup_is_idempotent():
    db = Database(":memory:")
    db.setup()
    db.setup()  # second call must not raise or change version
    row = db._conn.execute("SELECT version FROM schema_version").fetchone()
    assert row[0] == 1
    db.close()


def test_wal_mode_is_applied():
    # WAL pragma only works on real files, not :memory:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        with Database(path) as db:
            db.setup()
            result = db._conn.execute("PRAGMA journal_mode").fetchone()
            assert result[0] == "wal"
    finally:
        os.unlink(path)


def test_deadlines_table_has_notified_at_column():
    with make_db() as db:
        cols = [
            row[1]
            for row in db._conn.execute("PRAGMA table_info(deadlines)").fetchall()
        ]
        assert "notified_at" in cols


def test_deadlines_table_exists():
    with make_db() as db:
        db._conn.execute("SELECT * FROM deadlines").fetchall()  # must not raise


def test_sync_log_table_exists():
    with make_db() as db:
        db._conn.execute("SELECT * FROM sync_log").fetchall()  # must not raise


def test_context_manager_closes_connection():
    with Database(":memory:") as db:
        db.setup()
    # After exiting context, connection should be closed
    try:
        db._conn.execute("SELECT 1")
        assert False, "Expected exception — connection should be closed"
    except Exception:
        pass  # expected


# ---------------------------------------------------------------------------
# Day 2: Migration 2 — announcements + grades tables
# ---------------------------------------------------------------------------


def test_schema_version_is_5_after_full_migration():
    with make_db() as db:
        row = db._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row[0] == 6


def test_announcements_table_exists():
    with make_db() as db:
        db._conn.execute("SELECT * FROM announcements").fetchall()  # must not raise


def test_announcements_table_has_required_columns():
    with make_db() as db:
        cols = [
            row[1]
            for row in db._conn.execute("PRAGMA table_info(announcements)").fetchall()
        ]
        assert "id" in cols
        assert "course" in cols
        assert "title" in cols
        assert "body" in cols
        assert "posted_at" in cols
        assert "read_at" in cols


def test_grades_table_exists():
    with make_db() as db:
        db._conn.execute("SELECT * FROM grades").fetchall()  # must not raise


def test_grades_table_has_required_columns():
    with make_db() as db:
        cols = [
            row[1]
            for row in db._conn.execute("PRAGMA table_info(grades)").fetchall()
        ]
        assert "id" in cols
        assert "course" in cols
        assert "item" in cols
        assert "score" in cols
        assert "out_of" in cols
        assert "status" in cols
        assert "notified_at" in cols


# ---------------------------------------------------------------------------
# Day 2: CRUD — upsert_deadline
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta, timezone

from bb.adapters.base import Announcement, Deadline, GradeItem


def _deadline(
    id: str = "dl-1",
    course: str = "BTP200",
    title: str = "Lab 1",
    days_from_now: float = 3.0,
    source: str = "ical",
) -> Deadline:
    due = datetime.now(timezone.utc) + timedelta(days=days_from_now)
    return Deadline(id=id, course=course, title=title, due_at=due, source=source)


def _announcement(
    id: str = "ann-1",
    course: str = "BTP200",
    title: str = "Midterm info",
    body: str = "Midterm is next week.",
    hours_ago: float = 1.0,
) -> Announcement:
    posted = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return Announcement(id=id, course=course, title=title, body=body, posted_at=posted, read_at=None)


def _grade(
    id: str = "gr-1",
    course: str = "BTP200",
    item: str = "Lab 1",
    score: float = 18.0,
    out_of: float = 20.0,
    status: str = "graded",
) -> GradeItem:
    return GradeItem(id=id, course=course, item=item, score=score, out_of=out_of, status=status)


def test_upsert_deadline_inserts_new_record():
    with make_db() as db:
        db.upsert_deadline(_deadline())
        count = db._conn.execute("SELECT COUNT(*) FROM deadlines").fetchone()[0]
        assert count == 1


def test_upsert_deadline_is_idempotent():
    with make_db() as db:
        dl = _deadline()
        db.upsert_deadline(dl)
        db.upsert_deadline(dl)  # same id — should not create a duplicate
        count = db._conn.execute("SELECT COUNT(*) FROM deadlines").fetchone()[0]
        assert count == 1


def test_upsert_deadline_updates_existing_title():
    with make_db() as db:
        db.upsert_deadline(_deadline(title="Old title"))
        db.upsert_deadline(_deadline(title="New title"))
        row = db._conn.execute("SELECT title FROM deadlines WHERE id='dl-1'").fetchone()
        assert row[0] == "New title"


def test_upsert_deadline_stores_correct_fields():
    with make_db() as db:
        dl = _deadline(id="dl-x", course="OOP244", title="Assignment 2", source="stream")
        db.upsert_deadline(dl)
        row = db._conn.execute(
            "SELECT id, course, title, source FROM deadlines WHERE id='dl-x'"
        ).fetchone()
        assert row[0] == "dl-x"
        assert row[1] == "OOP244"
        assert row[2] == "Assignment 2"
        assert row[3] == "stream"


# ---------------------------------------------------------------------------
# Day 2: CRUD — upsert_announcement
# ---------------------------------------------------------------------------


def test_upsert_announcement_inserts_new_record():
    with make_db() as db:
        db.upsert_announcement(_announcement())
        count = db._conn.execute("SELECT COUNT(*) FROM announcements").fetchone()[0]
        assert count == 1


def test_upsert_announcement_is_idempotent():
    with make_db() as db:
        ann = _announcement()
        db.upsert_announcement(ann)
        db.upsert_announcement(ann)
        count = db._conn.execute("SELECT COUNT(*) FROM announcements").fetchone()[0]
        assert count == 1


def test_upsert_announcement_updates_body():
    with make_db() as db:
        db.upsert_announcement(_announcement(body="Old body"))
        db.upsert_announcement(_announcement(body="Updated body"))
        row = db._conn.execute("SELECT body FROM announcements WHERE id='ann-1'").fetchone()
        assert row[0] == "Updated body"


def test_upsert_announcement_read_at_is_null_by_default():
    with make_db() as db:
        db.upsert_announcement(_announcement())
        row = db._conn.execute("SELECT read_at FROM announcements WHERE id='ann-1'").fetchone()
        assert row[0] is None


# ---------------------------------------------------------------------------
# Day 2: CRUD — upsert_grade
# ---------------------------------------------------------------------------


def test_upsert_grade_inserts_new_record():
    with make_db() as db:
        db.upsert_grade(_grade())
        count = db._conn.execute("SELECT COUNT(*) FROM grades").fetchone()[0]
        assert count == 1


def test_upsert_grade_is_idempotent():
    with make_db() as db:
        g = _grade()
        db.upsert_grade(g)
        db.upsert_grade(g)
        count = db._conn.execute("SELECT COUNT(*) FROM grades").fetchone()[0]
        assert count == 1


def test_upsert_grade_updates_score():
    with make_db() as db:
        db.upsert_grade(_grade(score=15.0))
        db.upsert_grade(_grade(score=19.0))
        row = db._conn.execute("SELECT score FROM grades WHERE id='gr-1'").fetchone()
        assert row[0] == 19.0


def test_upsert_grade_stores_correct_fields():
    with make_db() as db:
        db.upsert_grade(_grade(course="OOP244", item="Midterm", score=82.0, out_of=100.0))
        row = db._conn.execute(
            "SELECT course, item, score, out_of, status FROM grades WHERE id='gr-1'"
        ).fetchone()
        assert row[0] == "OOP244"
        assert row[1] == "Midterm"
        assert row[2] == 82.0
        assert row[3] == 100.0
        assert row[4] == "graded"


# ---------------------------------------------------------------------------
# Day 2: Query helpers
# ---------------------------------------------------------------------------


def test_get_upcoming_deadlines_returns_deadlines_within_window():
    with make_db() as db:
        db.upsert_deadline(_deadline(id="dl-near", days_from_now=3))
        results = db.get_upcoming_deadlines(days=7)
        ids = [d.id for d in results]
        assert "dl-near" in ids


def test_get_upcoming_deadlines_excludes_past_deadlines():
    with make_db() as db:
        db.upsert_deadline(_deadline(id="dl-past", days_from_now=-1))
        results = db.get_upcoming_deadlines(days=7)
        ids = [d.id for d in results]
        assert "dl-past" not in ids


def test_get_upcoming_deadlines_excludes_beyond_window():
    with make_db() as db:
        db.upsert_deadline(_deadline(id="dl-far", days_from_now=10))
        results = db.get_upcoming_deadlines(days=7)
        ids = [d.id for d in results]
        assert "dl-far" not in ids


def test_get_upcoming_deadlines_sorted_by_due_at():
    with make_db() as db:
        db.upsert_deadline(_deadline(id="dl-later", days_from_now=5))
        db.upsert_deadline(_deadline(id="dl-sooner", days_from_now=1))
        results = db.get_upcoming_deadlines(days=7)
        ids = [d.id for d in results]
        assert ids.index("dl-sooner") < ids.index("dl-later")


def test_get_upcoming_deadlines_returns_deadline_objects():
    with make_db() as db:
        db.upsert_deadline(_deadline())
        results = db.get_upcoming_deadlines(days=7)
        assert len(results) == 1
        assert isinstance(results[0], Deadline)
        assert results[0].id == "dl-1"


def test_get_recent_announcements_returns_announcement_objects():
    with make_db() as db:
        db.upsert_announcement(_announcement())
        results = db.get_recent_announcements(limit=10)
        assert len(results) == 1
        assert isinstance(results[0], Announcement)
        assert results[0].id == "ann-1"


def test_get_recent_announcements_respects_limit():
    with make_db() as db:
        for i in range(5):
            db.upsert_announcement(_announcement(id=f"ann-{i}", title=f"Ann {i}", hours_ago=float(i)))
        results = db.get_recent_announcements(limit=3)
        assert len(results) == 3


def test_get_recent_announcements_returns_latest_first():
    with make_db() as db:
        db.upsert_announcement(_announcement(id="ann-old", hours_ago=10))
        db.upsert_announcement(_announcement(id="ann-new", hours_ago=1))
        results = db.get_recent_announcements(limit=10)
        ids = [a.id for a in results]
        assert ids.index("ann-new") < ids.index("ann-old")
