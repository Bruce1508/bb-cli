from contextlib import ExitStack
from unittest.mock import patch

import typer
from typer.testing import CliRunner

from bb.cli import app

runner = CliRunner()


def _run_setup(tmp_path, answer: str, fail_on: str | None = None) -> tuple[list[str], object]:
    calls: list[str] = []

    def step(name):
        def _f(*a, **kw):
            calls.append(name)
            if name == fail_on:
                raise typer.Exit(1)
        return _f

    with ExitStack() as stack:
        stack.enter_context(patch("bb.config.BB_DIR", tmp_path))
        for target, name in [
            ("bb.cli.init", "init"), ("bb.cli.setup_browsers", "browsers"),
            ("bb.cli._auth_if_needed", "auth"), ("bb.cli.sync", "sync"),
            ("bb.cli.auto_setup", "auto"),
        ]:
            stack.enter_context(patch(target, side_effect=step(name)))
        stack.enter_context(patch("bb.cli._print_ai_status"))
        result = runner.invoke(app, ["setup"], input=answer)
    return calls, result


def test_setup_runs_all_steps_in_order(tmp_path):
    calls, result = _run_setup(tmp_path, "y\n")
    assert result.exit_code == 0, result.output
    assert calls == ["init", "browsers", "auth", "sync", "auto"]


def test_setup_stops_at_failed_step(tmp_path):
    calls, result = _run_setup(tmp_path, "y\n", fail_on="auth")
    assert result.exit_code == 1
    assert calls == ["init", "browsers", "auth"]
    assert "bb setup" in result.output  # tells the user how to resume


def test_setup_skips_auto_sync_when_declined(tmp_path):
    calls, _ = _run_setup(tmp_path, "n\n")
    assert "auto" not in calls
