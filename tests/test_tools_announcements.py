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
