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
    db = Database(tmp_path / "bb.db")
    db.setup()
    db.upsert_deadline(Deadline("d1", "BTP200", "Lab [4]",
                                datetime.now(timezone.utc) + timedelta(hours=5), "ical"))
    db.close()
    result = _invoke(tmp_path, [])
    assert result.exit_code == 0, result.output
    assert "Today" in result.output
    assert "Lab [4]" in result.output  # markup in titles is escaped, not swallowed


def test_today_empty_state(tmp_path):
    result = _invoke(tmp_path, ["today"])
    assert result.exit_code == 0, result.output
    assert "Nothing due in the next 48h" in result.output
    assert "never synced" in result.output


def test_subcommands_still_work(tmp_path):
    result = _invoke(tmp_path, ["version"])
    assert result.exit_code == 0
    assert "bb-cli" in result.output
    assert "Today" not in result.output
