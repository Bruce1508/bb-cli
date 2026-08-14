from datetime import datetime, timezone
from unittest.mock import patch

from bb.changes import Change
from bb.db import Database


def test_render_digest_line_from_changes():
    from bb.cli import _render_change_digest
    now = datetime.now(timezone.utc).isoformat()
    changes = [
        Change("BTP200", "deadline", "d1", "Lab 4", "due_at", "due_moved",
               "2026-08-07T03:59:00+00:00", "2026-08-08T03:59:00+00:00", now),
    ]
    line = _render_change_digest(changes)
    assert "Lab 4" in line
    assert "BTP200" in line


def test_render_digest_empty_is_blank():
    from bb.cli import _render_change_digest
    assert _render_change_digest([]) == ""


def test_notify_changes_dedups(tmp_path):
    from bb.cli import _notify_changes
    db = Database(tmp_path / "bb.db")
    db.setup()
    now = datetime.now(timezone.utc).isoformat()
    change = Change("BTP200", "deadline", "d1", "Lab 4", "due_at", "due_moved",
                    "a", "b", now)
    with patch("bb.cli.dispatch_notify") as m:
        _notify_changes(db, [change], provider="terminal", ntfy_topic=None)
        _notify_changes(db, [change], provider="terminal", ntfy_topic=None)
    assert m.call_count == 1  # second call deduped within cooldown
