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
    assert result.exit_code == 75, result.output  # EX_TEMPFAIL: callers must not see success
    assert "Another bb sync is running" in result.output


def test_lock_is_released_after_a_sync(tmp_path):
    first = _sync(tmp_path)
    second = _sync(tmp_path)
    assert "Another bb sync is running" not in first.output + second.output


def test_ical_only_sync_exits_1_when_ical_fails(tmp_path):
    from bb.config import BBConfig
    with patch("bb.config.BB_DIR", tmp_path), patch("bb.notify.terminal.notify"), \
         patch("bb.cli.load_config", return_value=BBConfig(ical_url="https://x/feed.ics")), \
         patch("bb.sync.sync_ical", side_effect=RuntimeError("feed down")):
        result = runner.invoke(app, ["sync", "--ical-only"])
    assert result.exit_code == 1, result.output
    assert "iCal sync failed" in result.output


def test_ical_only_sync_exits_0_when_ical_works(tmp_path):
    from bb.config import BBConfig
    with patch("bb.config.BB_DIR", tmp_path), patch("bb.notify.terminal.notify"), \
         patch("bb.cli.load_config", return_value=BBConfig(ical_url="https://x/feed.ics")), \
         patch("bb.sync.sync_ical", return_value=(1, 0)):
        result = runner.invoke(app, ["sync", "--ical-only"])
    assert result.exit_code == 0, result.output
