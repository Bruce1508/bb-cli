import fcntl
from unittest.mock import patch

from typer.testing import CliRunner

from bb.cli import app

runner = CliRunner()


def _sync(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path), patch("bb.notify.terminal.notify"):
        return runner.invoke(app, ["sync", "--ical-only"])


def test_sync_skips_when_another_sync_holds_the_lock(tmp_path):
    with open(tmp_path / "sync.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = _sync(tmp_path)
    assert result.exit_code == 0, result.output
    assert "Another bb sync is running" in result.output


def test_lock_is_released_after_a_sync(tmp_path):
    first = _sync(tmp_path)
    second = _sync(tmp_path)
    assert "Another bb sync is running" not in first.output + second.output
