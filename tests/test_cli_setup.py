from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import typer
from typer.testing import CliRunner

from bb.cli import _auth_if_needed, _first_sync_succeeded, app
from bb.db import Database

runner = CliRunner()


def _run_setup(
    tmp_path, answer: str, fail_on: str | None = None, first_sync_ok: bool = True,
    raise_on: BaseException | None = None,
) -> tuple[list[str], dict, object]:
    calls: list[str] = []
    mocks: dict = {}

    def step(name):
        def _f(*a, **kw):
            calls.append(name)
            if name == fail_on:
                raise raise_on or typer.Exit(1)
        return _f

    with ExitStack() as stack:
        stack.enter_context(patch("bb.config.BB_DIR", tmp_path))
        for target, name in [
            ("bb.cli.init", "init"), ("bb.cli.setup_browsers", "browsers"),
            ("bb.cli._auth_if_needed", "auth"), ("bb.cli.sync", "sync"),
            ("bb.cli.auto_setup", "auto"),
        ]:
            mocks[name] = stack.enter_context(
                patch(target, MagicMock(side_effect=step(name)))
            )
        stack.enter_context(patch("bb.cli._print_ai_status"))
        stack.enter_context(patch("bb.cli._first_sync_succeeded", return_value=first_sync_ok))
        result = runner.invoke(app, ["setup"], input=answer)
    return calls, mocks, result


def test_setup_runs_all_steps_in_order(tmp_path):
    calls, mocks, result = _run_setup(tmp_path, "y\n")
    assert result.exit_code == 0, result.output
    assert calls == ["init", "browsers", "auth", "sync", "auto"]
    mocks["sync"].assert_called_once_with(ical_only=False, dry_run=False, refresh_only=False)
    mocks["auto"].assert_called_once_with(disable=False, interval=0)


def test_setup_stops_at_failed_step(tmp_path):
    calls, _, result = _run_setup(tmp_path, "y\n", fail_on="auth")
    assert result.exit_code == 1
    assert calls == ["init", "browsers", "auth"]
    assert "bb setup" in result.output  # tells the user how to resume


def test_setup_hints_resume_on_abort(tmp_path):
    calls, _, result = _run_setup(tmp_path, "y\n", fail_on="init", raise_on=typer.Abort())
    assert result.exit_code != 0
    assert calls == ["init"]
    assert "bb setup" in result.output


def test_setup_skips_auto_sync_when_declined(tmp_path):
    calls, _, result = _run_setup(tmp_path, "n\n")
    assert result.exit_code == 0, result.output
    assert "sync" in calls
    assert "auto" not in calls


def test_setup_stops_when_first_sync_failed(tmp_path):
    calls, _, result = _run_setup(tmp_path, "y\n", first_sync_ok=False)
    assert result.exit_code == 1
    assert "First sync didn't succeed" in result.output
    assert "auto" not in calls


def test_auth_if_needed_skips_login_when_fresh(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path), \
         patch("bb.security.session.SessionManager.check_session_age", return_value="fresh"), \
         patch("bb.cli.auth") as auth:
        _auth_if_needed()
    auth.assert_not_called()


def test_auth_if_needed_logs_in_when_expired(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path), \
         patch("bb.security.session.SessionManager.check_session_age", return_value="expired"), \
         patch("bb.cli.auth") as auth:
        _auth_if_needed()
    auth.assert_called_once()


def test_first_sync_succeeded_checks_sync_log(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        with Database(tmp_path / "bb.db") as db:
            db.setup()
            db.log_sync("ical", 0, 0, error="x")
        assert _first_sync_succeeded("2000-01-01T00:00:00+00:00") is False
        with Database(tmp_path / "bb.db") as db:
            db.log_sync("ical", 1, 0)
        assert _first_sync_succeeded("2000-01-01T00:00:00+00:00") is True
        assert _first_sync_succeeded("2999-01-01T00:00:00+00:00") is False
