from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from bb.adapters.base import Deadline
from bb.config import NotificationConfig
from bb.db import Database
from bb.reminders import pending_reminders, send_reminders

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def _d(hours: float, did: str = "d1") -> Deadline:
    return Deadline(id=did, course="BTP200", title="Lab 4",
                    due_at=NOW + timedelta(hours=hours), source="ical")


def test_nothing_beyond_24h():
    assert pending_reminders([_d(30)], NOW) == []


def test_past_deadline_ignored():
    assert pending_reminders([_d(-1)], NOW) == []


def test_24h_window():
    [r] = pending_reminders([_d(20)], NOW)
    assert (r.window, r.priority) == ("24h", "high")
    assert "BTP200" in r.message and "Lab 4" in r.message and "20h" in r.message


def test_6h_window_wins_over_24h():
    [r] = pending_reminders([_d(3)], NOW)
    assert (r.window, r.priority) == ("6h", "urgent")


def test_under_one_hour_shows_minutes():
    [r] = pending_reminders([_d(0.5)], NOW)
    assert "30m" in r.message


def test_moved_deadline_gets_new_key():
    [a] = pending_reminders([_d(20)], NOW)
    [b] = pending_reminders([_d(22)], NOW)
    assert a.key != b.key


def test_send_reminders_sends_each_window_once(tmp_path):
    db = Database(tmp_path / "bb.db")
    db.setup()
    db.upsert_deadline(Deadline("d1", "BTP200", "Lab 4",
                                datetime.now(timezone.utc) + timedelta(hours=3), "ical"))
    with patch("bb.reminders.dispatch_notify") as m:
        assert send_reminders(db, NotificationConfig()) == 1
        assert send_reminders(db, NotificationConfig()) == 0
    assert m.call_args.kwargs["priority"] == "urgent"
    db.close()


def test_sync_ical_only_sends_reminders(tmp_path):
    from typer.testing import CliRunner

    from bb.cli import app
    db = Database(tmp_path / "bb.db")
    db.setup()
    db.upsert_deadline(Deadline("d1", "BTP200", "Lab 4",
                                datetime.now(timezone.utc) + timedelta(hours=3), "ical"))
    db.close()
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.reminders.dispatch_notify") as m,
        patch("bb.notify.terminal.notify"),  # no real desktop popups (digest in Task 4)
    ):
        result = CliRunner().invoke(app, ["sync", "--ical-only"])
    assert result.exit_code == 0, result.output
    m.assert_called_once()
    assert "reminder" in result.output


def test_sync_dead_session_still_reminds(tmp_path):
    from typer.testing import CliRunner

    from bb.cli import app
    from bb.security.session import SessionError
    db = Database(tmp_path / "bb.db")
    db.setup()
    db.upsert_deadline(Deadline("d1", "BTP200", "Lab 4",
                                datetime.now(timezone.utc) + timedelta(hours=3), "ical"))
    db.close()
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.reminders.dispatch_notify") as m,
        patch("bb.notify.terminal.notify"),
        patch("bb.cli.dispatch_notify"),  # session-expired notice
        patch("bb.sync.preflight_session", side_effect=SessionError("dead")),
    ):
        result = CliRunner().invoke(app, ["sync"])
    assert result.exit_code == 1, result.output
    m.assert_called_once()


def test_reminder_failure_does_not_fail_sync(tmp_path):
    from typer.testing import CliRunner

    from bb.cli import app
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.notify.terminal.notify"),
        patch("bb.reminders.send_reminders", side_effect=RuntimeError("boom")),
    ):
        result = CliRunner().invoke(app, ["sync", "--ical-only"])
    assert result.exit_code == 0, result.output
    assert "Reminders failed" in result.output
