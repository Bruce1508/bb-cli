from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from bb.adapters.base import Announcement, Deadline
from bb.briefing import briefing_text
from bb.db import Database
from bb.tools.queries import get_briefing

EMPTY = {"urgent_deadlines": [], "later_this_week": 0, "recent_changes": [],
         "unread_announcements": [], "unread_count": 0, "last_sync": None}


def _seed(tmp_path, hours_list):
    db = Database(tmp_path / "bb.db")
    db.setup()
    now = datetime.now(timezone.utc)
    for i, h in enumerate(hours_list):
        db.upsert_deadline(Deadline(f"d{i}", "BTP200", f"Lab {i}", now + timedelta(hours=h), "ical"))
    db.close()


def test_briefing_splits_urgent_from_later(tmp_path):
    _seed(tmp_path, [5, 30, 100])
    with patch("bb.config.BB_DIR", tmp_path):
        b = get_briefing()
    assert [d["title"] for d in b["urgent_deadlines"]] == ["Lab 0", "Lab 1"]
    assert b["later_this_week"] == 1


def test_briefing_missing_db_is_empty(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path / "nope"):
        b = get_briefing()
    assert b["urgent_deadlines"] == [] and b["later_this_week"] == 0


def test_briefing_text_empty():
    assert briefing_text(EMPTY) == "Nothing due in the next 48h."


def test_briefing_text_lists_and_truncates():
    urgent = [{"course": "BTP200", "title": f"Lab {i}", "when": "due tomorrow"} for i in range(5)]
    text = briefing_text({**EMPTY, "urgent_deadlines": urgent,
                          "unread_announcements": [{}, {}], "unread_count": 2})
    assert "Lab 0" in text and "Lab 2" in text and "Lab 3" not in text
    assert "+2 more" in text
    assert "2 unread announcements" in text


def test_briefing_includes_recently_overdue_as_urgent(tmp_path):
    _seed(tmp_path, [-2, 5])
    with patch("bb.config.BB_DIR", tmp_path):
        b = get_briefing()
    whens = [d["when"] for d in b["urgent_deadlines"]]
    assert len(whens) == 2 and whens[0].startswith("was due")


def test_briefing_text_heading_and_more_this_week():
    urgent = [{"course": "BTP200", "title": "Lab 4", "when": "was due 2h ago (today)"}]
    text = briefing_text({**EMPTY, "urgent_deadlines": urgent, "later_this_week": 3})
    assert text.startswith("Due soon: BTP200 Lab 4")
    assert "3 more this week" in text


from bb.briefing import send_daily_digest  # noqa: E402
from bb.config import NotificationConfig  # noqa: E402


def _db(tmp_path):
    db = Database(tmp_path / "bb.db")
    db.setup()
    return db


def test_digest_sent_once_per_day(tmp_path):
    db = _db(tmp_path)
    at8 = datetime(2026, 11, 16, 8, 0).astimezone()
    with (
        patch("bb.briefing.dispatch_notify") as m,
        patch("bb.tools.queries.get_briefing", return_value=EMPTY),
    ):
        assert send_daily_digest(db, NotificationConfig(), at8) is True
        assert send_daily_digest(db, NotificationConfig(), at8.replace(hour=12)) is False
    assert m.call_count == 1
    assert m.call_args.args[2] == "Nothing due in the next 48h."


def test_digest_waits_for_digest_hour(tmp_path):
    db = _db(tmp_path)
    at6 = datetime(2026, 11, 16, 6, 0).astimezone()
    with patch("bb.briefing.dispatch_notify") as m:
        assert send_daily_digest(db, NotificationConfig(digest_hour=7), at6) is False
    m.assert_not_called()


def test_digest_can_be_disabled(tmp_path):
    db = _db(tmp_path)
    at8 = datetime(2026, 11, 16, 8, 0).astimezone()
    with patch("bb.briefing.dispatch_notify") as m:
        assert send_daily_digest(db, NotificationConfig(daily_digest=False), at8) is False
    m.assert_not_called()


def test_briefing_reports_true_unread_count(tmp_path):
    db = Database(tmp_path / "bb.db")
    db.setup()
    now = datetime.now(timezone.utc)
    for i in range(12):
        db.upsert_announcement(Announcement(f"a{i}", "BTP200", f"Ann {i}", "b", now, None))
    db.close()
    with patch("bb.config.BB_DIR", tmp_path):
        b = get_briefing()
    assert b["unread_count"] == 12
    assert len(b["unread_announcements"]) == 5
    assert "12 unread announcements" in briefing_text(b)


def test_briefing_missing_db_unread_count_zero(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path / "nope"):
        assert get_briefing()["unread_count"] == 0


def test_briefing_last_sync_is_last_successful(tmp_path):
    db = Database(tmp_path / "bb.db")
    db.setup()
    db._conn.execute(
        "INSERT INTO sync_log (synced_at, source, items_new, items_updated, error)"
        " VALUES ('2026-01-01T10:00:00+00:00', 'ical', 1, 0, NULL)")
    db._conn.execute(
        "INSERT INTO sync_log (synced_at, source, items_new, items_updated, error)"
        " VALUES ('2026-01-02T10:00:00+00:00', 'ical', 0, 0, 'boom')")
    db._conn.commit()
    db.close()
    with patch("bb.config.BB_DIR", tmp_path):
        assert get_briefing()["last_sync"] == "2026-01-01T10:00:00+00:00"
