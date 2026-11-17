from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from bb.adapters.base import Deadline
from bb.briefing import briefing_text
from bb.db import Database
from bb.tools.queries import get_briefing

EMPTY = {"urgent_deadlines": [], "later_this_week": 0, "recent_changes": [],
         "unread_announcements": [], "last_sync": None}


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
                          "unread_announcements": [{}, {}]})
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
