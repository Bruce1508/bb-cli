from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from typer.testing import CliRunner

from bb.adapters.base import Deadline
from bb.cli import app
from bb.db import Database

runner = CliRunner()


def _invoke(tmp_path, args):
    with patch("bb.config.BB_DIR", tmp_path), patch("bb.cli._warn_if_session_stale"):
        return runner.invoke(app, args)


def test_bare_bb_shows_briefing(tmp_path):
    (tmp_path / "config.toml").write_text("")  # a set-up user
    db = Database(tmp_path / "bb.db")
    db.setup()
    db.upsert_deadline(Deadline("d1", "BTP200", "Lab [4]",
                                datetime.now(timezone.utc) + timedelta(hours=5), "ical"))
    db.log_sync("ical", 1, 0)
    db.close()
    result = _invoke(tmp_path, [])
    assert result.exit_code == 0, result.output
    assert "Today" in result.output
    assert "Lab [4]" in result.output  # markup in titles is escaped, not swallowed


def test_today_empty_state(tmp_path):
    result = _invoke(tmp_path, ["today"])
    assert result.exit_code == 0, result.output
    assert "bb setup" in result.output
    assert "Nothing due" not in result.output


def test_configured_user_without_successful_sync_sees_deadlines(tmp_path):
    """import-ical writes config + deadlines but no sync_log row; failed syncs log only
    errors. Neither user should be told to re-run `bb setup` — show their data."""
    (tmp_path / "config.toml").write_text('ical_url = "https://x/feed.ics"\n')
    db = Database(tmp_path / "bb.db")
    db.setup()
    db.upsert_deadline(Deadline("d1", "BTP200", "Lab 4",
                                datetime.now(timezone.utc) + timedelta(hours=5), "ical"))
    db.log_sync("stream", 0, 0, error="session_expired")
    db.close()
    result = _invoke(tmp_path, [])
    assert result.exit_code == 0, result.output
    assert "Lab 4" in result.output
    assert "never synced" in result.output
    assert "bb setup" not in result.output


def test_today_lists_more_unread(tmp_path):
    from bb.adapters.base import Announcement
    (tmp_path / "config.toml").write_text("")  # a set-up user
    db = Database(tmp_path / "bb.db")
    db.setup()
    now = datetime.now(timezone.utc)
    for i in range(8):
        db.upsert_announcement(Announcement(f"a{i}", "BTP200", f"Ann {i}", "b", now, None))
    db.log_sync("ical", 1, 0)
    db.close()
    result = _invoke(tmp_path, ["today"])
    assert "+3 more unread" in result.output


def test_subcommands_still_work(tmp_path):
    result = _invoke(tmp_path, ["version"])
    assert result.exit_code == 0
    assert "bb-cli" in result.output
    assert "Today" not in result.output
