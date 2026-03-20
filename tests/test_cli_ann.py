"""
Tests for `bb ann` command in bb/cli.py

Strategy:
- Patch bb.config.BB_DIR → tmp_path
- Seed announcements with db.upsert_announcement
- Use typer.testing.CliRunner for full CLI invocation

Success criteria:
- exits 0 always
- empty DB: prints "No announcements found"
- --unread with none unread: prints "No unread announcements"
- with rows: shows course, title, relative time (Xm ago / Xh ago / Xd ago)
- --unread filter: only shows announcements where read_at is None
- unread announcement titles include "bold" markup or display correctly
- read announcement: read_at set → still shown without --unread flag
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from bb.adapters.base import Announcement
from bb.cli import app
from bb.db import Database

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_announcements(tmp_path, announcements: list[Announcement]) -> None:
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        for a in announcements:
            db.upsert_announcement(a)


def _make_announcement(
    id: str = "ann-1",
    course: str = "BTI325",
    title: str = "Lab 1 Updated",
    body: str = "New requirements posted.",
    posted_at: datetime | None = None,
    read_at: datetime | None = None,
) -> Announcement:
    if posted_at is None:
        posted_at = datetime.now(timezone.utc) - timedelta(hours=2)
    return Announcement(
        id=id,
        course=course,
        title=title,
        body=body,
        posted_at=posted_at,
        read_at=read_at,
    )


def _invoke(tmp_path, *args):
    with patch("bb.config.BB_DIR", tmp_path):
        return runner.invoke(app, ["ann", *args])


# ---------------------------------------------------------------------------
# Exit code
# ---------------------------------------------------------------------------


def test_ann_exits_zero_on_empty_db(tmp_path):
    _seed_announcements(tmp_path, [])
    result = _invoke(tmp_path)
    assert result.exit_code == 0, result.output


def test_ann_exits_zero_with_rows(tmp_path):
    _seed_announcements(tmp_path, [_make_announcement()])
    result = _invoke(tmp_path)
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# Empty state messages
# ---------------------------------------------------------------------------


def test_ann_shows_no_announcements_when_empty(tmp_path):
    _seed_announcements(tmp_path, [])
    result = _invoke(tmp_path)
    assert "No announcements found" in result.output


def test_ann_unread_shows_no_unread_when_all_read(tmp_path):
    now = datetime.now(timezone.utc)
    _seed_announcements(
        tmp_path,
        [_make_announcement(read_at=now)],
    )
    result = _invoke(tmp_path, "--unread")
    assert "No unread announcements" in result.output


# ---------------------------------------------------------------------------
# Row content
# ---------------------------------------------------------------------------


def test_ann_shows_course_code(tmp_path):
    _seed_announcements(tmp_path, [_make_announcement(course="BTI325")])
    result = _invoke(tmp_path)
    assert "BTI325" in result.output


def test_ann_shows_announcement_title(tmp_path):
    _seed_announcements(tmp_path, [_make_announcement(title="Important Update")])
    result = _invoke(tmp_path)
    assert "Important Update" in result.output


def test_ann_shows_hours_ago_for_recent_posting(tmp_path):
    posted_at = datetime.now(timezone.utc) - timedelta(hours=3)
    _seed_announcements(tmp_path, [_make_announcement(posted_at=posted_at)])
    result = _invoke(tmp_path)
    assert "h ago" in result.output


def test_ann_shows_days_ago_for_old_posting(tmp_path):
    posted_at = datetime.now(timezone.utc) - timedelta(days=5)
    _seed_announcements(tmp_path, [_make_announcement(posted_at=posted_at)])
    result = _invoke(tmp_path)
    assert "d ago" in result.output


def test_ann_shows_minutes_ago_for_very_recent_posting(tmp_path):
    posted_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    _seed_announcements(tmp_path, [_make_announcement(posted_at=posted_at)])
    result = _invoke(tmp_path)
    assert "m ago" in result.output


# ---------------------------------------------------------------------------
# --unread filter
# ---------------------------------------------------------------------------


def test_ann_unread_shows_unread_announcement(tmp_path):
    _seed_announcements(
        tmp_path,
        [_make_announcement(id="ann-1", title="Unread News", read_at=None)],
    )
    result = _invoke(tmp_path, "--unread")
    assert "Unread News" in result.output


def test_ann_unread_hides_read_announcements(tmp_path):
    now = datetime.now(timezone.utc)
    _seed_announcements(
        tmp_path,
        [
            _make_announcement(id="ann-1", title="Already Read", read_at=now),
            _make_announcement(id="ann-2", title="New Announcement", read_at=None),
        ],
    )
    result = _invoke(tmp_path, "--unread")
    assert "Already Read" not in result.output
    assert "New Announcement" in result.output


def test_ann_without_unread_flag_shows_all_announcements(tmp_path):
    now = datetime.now(timezone.utc)
    _seed_announcements(
        tmp_path,
        [
            _make_announcement(id="ann-1", title="Already Read", read_at=now),
            _make_announcement(id="ann-2", title="New Announcement", read_at=None),
        ],
    )
    result = _invoke(tmp_path)
    assert "Already Read" in result.output
    assert "New Announcement" in result.output


# ---------------------------------------------------------------------------
# Multiple items
# ---------------------------------------------------------------------------


def test_ann_shows_multiple_announcements(tmp_path):
    _seed_announcements(
        tmp_path,
        [
            _make_announcement(id="ann-1", title="First Post"),
            _make_announcement(id="ann-2", title="Second Post"),
        ],
    )
    result = _invoke(tmp_path)
    assert "First Post" in result.output
    assert "Second Post" in result.output
