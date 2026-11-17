from datetime import datetime, timezone
from unittest.mock import patch

from bb.adapters.base import Announcement
from bb.db import Database
from bb.tools.queries import get_announcements


def test_get_announcements_includes_body(tmp_path):
    db = Database(tmp_path / "bb.db")
    db.setup()
    db.upsert_announcement(Announcement(
        id="a1", course="BTP200", title="Midterm moved",
        body="The midterm is now on Friday in room A1001.",
        posted_at=datetime(2026, 11, 10, tzinfo=timezone.utc), read_at=None,
    ))
    db.close()
    with patch("bb.config.BB_DIR", tmp_path):
        out = get_announcements()
    assert out[0]["body"] == "The midterm is now on Friday in room A1001."
    assert out[0]["read"] is False


def _seed(tmp_path, n, read_first=False):
    db = Database(tmp_path / "bb.db")
    db.setup()
    for i in range(n):
        db.upsert_announcement(Announcement(
            id=f"a{i}", course="BTP200", title=f"T{i}", body="b",
            posted_at=datetime(2026, 11, 10 + i, tzinfo=timezone.utc),
            read_at=datetime(2026, 11, 20, tzinfo=timezone.utc) if read_first and i == 0 else None,
        ))
    db.close()


def test_get_announcements_limit_is_clamped(tmp_path):
    _seed(tmp_path, 3)
    with patch("bb.config.BB_DIR", tmp_path):
        assert len(get_announcements(limit=-1)) == 1
        assert len(get_announcements(limit=1000)) == 3


def test_get_announcements_unread_passthrough(tmp_path):
    _seed(tmp_path, 2, read_first=True)
    with patch("bb.config.BB_DIR", tmp_path):
        out = get_announcements(unread=True, limit=5)
    assert [a["title"] for a in out] == ["T1"]
