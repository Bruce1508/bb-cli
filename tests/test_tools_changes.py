from datetime import datetime, timezone
from unittest.mock import patch

from bb.changes import Change
from bb.db import Database
from bb.tools.queries import get_recent_changes


def test_get_recent_changes_returns_dicts(tmp_path):
    db = Database(tmp_path / "bb.db")
    db.setup()
    db._record_change(Change("BTP200", "deadline", "d1", "Lab 4", "due_at",
                             "due_moved", "a", "b",
                             datetime.now(timezone.utc).isoformat()))
    db._conn.commit()
    db.close()
    with patch("bb.config.BB_DIR", tmp_path):
        out = get_recent_changes(days=30)
    assert len(out) == 1
    assert out[0]["title"] == "Lab 4"
    assert out[0]["change_type"] == "due_moved"


def test_get_recent_changes_missing_db_returns_empty(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path / "nope"):
        assert get_recent_changes() == []
