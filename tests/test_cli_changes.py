from datetime import datetime, timezone
from unittest.mock import patch

from typer.testing import CliRunner

from bb.changes import Change
from bb.cli import app
from bb.db import Database

runner = CliRunner()


def _seed(tmp_path):
    db = Database(tmp_path / "bb.db")
    db.setup()
    db._record_change(Change("BTP200", "deadline", "d1", "Lab 4", "due_at",
                             "due_moved", "a", "b",
                             datetime.now(timezone.utc).isoformat()))
    db._conn.commit()
    db.close()


def test_changes_default_shows_and_acknowledges(tmp_path):
    _seed(tmp_path)
    with patch("bb.config.BB_DIR", tmp_path), patch("bb.db.BB_DIR", tmp_path):
        r1 = runner.invoke(app, ["changes"])
        assert r1.exit_code == 0
        assert "Lab 4" in r1.stdout
        # second run: already acknowledged → nothing new
        r2 = runner.invoke(app, ["changes"])
        assert "Lab 4" not in r2.stdout


def test_changes_all_does_not_acknowledge(tmp_path):
    _seed(tmp_path)
    with patch("bb.config.BB_DIR", tmp_path), patch("bb.db.BB_DIR", tmp_path):
        runner.invoke(app, ["changes", "--all"])
        r2 = runner.invoke(app, ["changes", "--all"])
        assert "Lab 4" in r2.stdout  # still visible; --all never acks
