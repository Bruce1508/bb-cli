from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from bb.adapters.base import Deadline
from bb.db import Database
from bb.tools.queries import get_upcoming_deadlines, resolve_course


@pytest.fixture
def courses(tmp_path):
    db = Database(tmp_path / "bb.db")
    db.setup()
    db.upsert_course_map("BTP200", "_1", "Object-Oriented Software Development")
    db.upsert_course_map("WEB322", "_2", "Web Programming Tools and Frameworks")
    db.upsert_course_map("WEB422", "_3", "Web Programming for Apps and Services")
    db.upsert_deadline(Deadline("d1", "BTP200", "Lab 4",
                                datetime.now(timezone.utc) + timedelta(days=1), "ical"))
    db.close()
    with patch("bb.config.BB_DIR", tmp_path):
        yield


@pytest.mark.parametrize("text,expected", [
    ("BTP200", "BTP200"),
    ("btp200", "BTP200"),
    ("btp", "BTP200"),            # unique code prefix
    ("object", "BTP200"),         # display-name match
    ("frameworks", "WEB322"),
    ("web", "WEB"),               # ambiguous → no match, not "everything"
    ("programming", "PROGRAMMING"),
    ("xyz", "XYZ"),
    ("all", None),
    ("  ", None),
    (None, None),
])
def test_resolve_course(courses, text, expected):
    assert resolve_course(text) == expected


def test_tools_accept_loose_course_names(courses):
    assert [d["title"] for d in get_upcoming_deadlines(course="btp")] == ["Lab 4"]
    assert get_upcoming_deadlines(course="web") == []


def test_unmatched_course_cannot_become_a_path(courses):
    code = resolve_course("../../x")
    assert code and "/" not in code and "." not in code


def test_read_file_content_cannot_escape_bb_dir(tmp_path):
    from bb.tools.queries import read_file_content

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "f.pdf").write_bytes(b"%PDF secret")
    (tmp_path / "bb" / "files").mkdir(parents=True)  # as in a real ~/.bb
    with patch("bb.config.BB_DIR", tmp_path / "bb"), \
         patch("bb.tools.queries.pdfplumber.open") as opened:
        result = read_file_content("../../outside", "f")
    assert "error" in result
    opened.assert_not_called()
