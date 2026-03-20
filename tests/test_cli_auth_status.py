"""
Tests for `bb auth` and `bb status` commands in bb/cli.py

Strategy:
- bb auth: mock BlackboardUltraAdapter.authenticate to avoid real Playwright;
  mock load_config to avoid needing a real config.toml
- bb status: patch bb.config.BB_DIR → tmp_path; seed session.enc and/or bb.db as needed;
  mock time.time() to test session age display

Success criteria:
- bb auth: PlaywrightTimeout → exit 1; generic exception → exit 1 + prints error
- bb auth: prints LMS URL before attempting authentication
- bb status: always exits 0
- bb status: shows "expired" when no session file exists
- bb status: shows "fresh" / "uncertain" / "expired" based on session file age
- bb status: shows "not initialized" when bb.db is absent
- bb status: shows correct counts (N deadlines, M announcements, K grades)
- bb status: shows "never" for last sync when sync_log is empty
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from bb.adapters.base import Announcement, Deadline, GradeItem
from bb.cli import app
from bb.config import BBConfig, NotificationConfig
from bb.db import Database
from bb.security.session import FRESH_THRESHOLD, UNCERTAIN_THRESHOLD

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(lms_url: str = "https://learn.example.com") -> BBConfig:
    return BBConfig(
        lms_type="blackboard_ultra",
        lms_url=lms_url,
        notification=NotificationConfig(provider="terminal"),
    )


def _invoke_status(tmp_path, *extra_args: str):
    with patch("bb.config.BB_DIR", tmp_path):
        return runner.invoke(app, ["status", *extra_args])


def _seed_db(tmp_path, *, deadlines: int = 0, announcements: int = 0, grades: int = 0) -> None:
    now = datetime.now(timezone.utc)
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        for i in range(deadlines):
            db.upsert_deadline(
                Deadline(
                    id=f"dl-{i}",
                    course="BTI325",
                    title=f"Lab {i}",
                    due_at=now + timedelta(days=1),
                    source="ical",
                )
            )
        for i in range(announcements):
            db.upsert_announcement(
                Announcement(
                    id=f"ann-{i}",
                    course="BTI325",
                    title=f"Announcement {i}",
                    body="body text",
                    posted_at=now,
                    read_at=None,
                )
            )
        for i in range(grades):
            db.upsert_grade(
                GradeItem(
                    id=f"grade-{i}",
                    course="BTI325",
                    item=f"Lab {i}",
                    score=90.0,
                    out_of=100.0,
                    status="graded",
                )
            )


# ---------------------------------------------------------------------------
# bb status — exit code
# ---------------------------------------------------------------------------


def test_status_exits_zero_with_no_session_or_db(tmp_path):
    result = _invoke_status(tmp_path)
    assert result.exit_code == 0, result.output


def test_status_exits_zero_with_db_present(tmp_path):
    _seed_db(tmp_path)
    result = _invoke_status(tmp_path)
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# bb status — session age display
# ---------------------------------------------------------------------------


def test_status_shows_expired_when_no_session_file(tmp_path):
    result = _invoke_status(tmp_path)
    assert "expired" in result.output.lower()


def test_status_shows_fresh_when_session_is_new(tmp_path):
    session_path = tmp_path / "session.enc"
    session_path.write_bytes(b"fake-encrypted-content")
    mtime = session_path.stat().st_mtime
    with patch("bb.config.BB_DIR", tmp_path), patch("time.time", return_value=mtime + 60):
        result = runner.invoke(app, ["status"])
    assert "fresh" in result.output.lower()


def test_status_shows_uncertain_when_session_is_12h_old(tmp_path):
    session_path = tmp_path / "session.enc"
    session_path.write_bytes(b"fake-encrypted-content")
    mtime = session_path.stat().st_mtime
    with patch("bb.config.BB_DIR", tmp_path), patch(
        "time.time", return_value=mtime + 12 * 3600
    ):
        result = runner.invoke(app, ["status"])
    assert "uncertain" in result.output.lower()


def test_status_shows_expired_when_session_is_25h_old(tmp_path):
    session_path = tmp_path / "session.enc"
    session_path.write_bytes(b"fake-encrypted-content")
    mtime = session_path.stat().st_mtime
    with patch("bb.config.BB_DIR", tmp_path), patch(
        "time.time", return_value=mtime + 25 * 3600
    ):
        result = runner.invoke(app, ["status"])
    assert "expired" in result.output.lower()


# ---------------------------------------------------------------------------
# bb status — DB not initialized
# ---------------------------------------------------------------------------


def test_status_shows_not_initialized_when_no_db(tmp_path):
    result = _invoke_status(tmp_path)
    assert "not initialized" in result.output


def test_status_does_not_show_db_stats_when_no_db(tmp_path):
    result = _invoke_status(tmp_path)
    assert "deadlines" not in result.output


# ---------------------------------------------------------------------------
# bb status — DB stat counts
# ---------------------------------------------------------------------------


def test_status_shows_zero_deadlines_on_empty_db(tmp_path):
    _seed_db(tmp_path)
    result = _invoke_status(tmp_path)
    assert "0 deadlines" in result.output


def test_status_shows_correct_deadline_count(tmp_path):
    _seed_db(tmp_path, deadlines=3)
    result = _invoke_status(tmp_path)
    assert "3 deadlines" in result.output


def test_status_shows_correct_announcement_count(tmp_path):
    _seed_db(tmp_path, announcements=2)
    result = _invoke_status(tmp_path)
    assert "2 announcements" in result.output


def test_status_shows_correct_grades_count(tmp_path):
    _seed_db(tmp_path, grades=5)
    result = _invoke_status(tmp_path)
    assert "5 grades" in result.output


def test_status_shows_all_counts_together(tmp_path):
    _seed_db(tmp_path, deadlines=2, announcements=1, grades=4)
    result = _invoke_status(tmp_path)
    assert "2 deadlines" in result.output
    assert "1 announcement" in result.output
    assert "4 grades" in result.output


# ---------------------------------------------------------------------------
# bb status — last sync
# ---------------------------------------------------------------------------


def test_status_shows_never_when_sync_log_is_empty(tmp_path):
    _seed_db(tmp_path)
    result = _invoke_status(tmp_path)
    assert "never" in result.output


# ---------------------------------------------------------------------------
# bb auth — error paths (no real Playwright needed)
# ---------------------------------------------------------------------------


def test_auth_playwright_timeout_exits_1(tmp_path):
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.load_config", return_value=_make_config()),
        patch(
            "bb.adapters.blackboard_ultra.BlackboardUltraAdapter.authenticate",
            side_effect=PlaywrightTimeout("login timed out"),
        ),
    ):
        result = runner.invoke(app, ["auth"])
    assert result.exit_code == 1


def test_auth_generic_exception_exits_1(tmp_path):
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.load_config", return_value=_make_config()),
        patch(
            "bb.adapters.blackboard_ultra.BlackboardUltraAdapter.authenticate",
            side_effect=RuntimeError("network failure"),
        ),
    ):
        result = runner.invoke(app, ["auth"])
    assert result.exit_code == 1


def test_auth_generic_exception_prints_error_message(tmp_path):
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.load_config", return_value=_make_config()),
        patch(
            "bb.adapters.blackboard_ultra.BlackboardUltraAdapter.authenticate",
            side_effect=RuntimeError("network failure"),
        ),
    ):
        result = runner.invoke(app, ["auth"])
    assert "network failure" in result.output


def test_auth_prints_lms_url_before_attempting_login(tmp_path):
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.load_config", return_value=_make_config("https://learn.example.com")),
        patch(
            "bb.adapters.blackboard_ultra.BlackboardUltraAdapter.authenticate",
            side_effect=PlaywrightTimeout("timed out"),
        ),
    ):
        result = runner.invoke(app, ["auth"])
    assert "learn.example.com" in result.output
