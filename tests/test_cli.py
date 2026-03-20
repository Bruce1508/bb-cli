"""
Tests for bb/cli.py — bb init command

Success criteria:
- 'bb init' with default inputs exits with code 0
- config.toml is created at BB_DIR after init
- config.toml is parseable by load_config()
- config.toml reflects defaults (lms_type, lms_url, provider)
- bb.db is created at BB_DIR after init
- bb.db contains the 'deadlines' table
- Running 'bb init' twice is idempotent (no error, DB stays valid)
- Output contains success checkmarks for config and DB

Note: both bb.config.BB_DIR and bb.db.BB_DIR are patched to tmp_path
so tests never touch the real ~/.bb/ directory.
"""
import sqlite3
from unittest.mock import patch

import pytest
from typer.testing import CliRunner


runner = CliRunner()

# Wizard default inputs: accept LMS type (Enter), accept URL (Enter), accept notification (Enter)
DEFAULT_INPUTS = "\n\n\n"


def _invoke_init(tmp_path, inputs=DEFAULT_INPUTS):
    """Helper: invoke 'bb init' with both BB_DIR patches applied."""
    with patch("bb.config.BB_DIR", tmp_path), patch("bb.db.BB_DIR", tmp_path):
        from bb.cli import app

        return runner.invoke(app, ["init"], input=inputs)


# ---------------------------------------------------------------------------
# Exit code
# ---------------------------------------------------------------------------


def test_init_exits_with_zero(tmp_path):
    """'bb init' with default selections returns exit code 0."""
    result = _invoke_init(tmp_path)
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# config.toml
# ---------------------------------------------------------------------------


def test_init_creates_config_toml(tmp_path):
    """config.toml exists at BB_DIR after 'bb init'."""
    _invoke_init(tmp_path)
    assert (tmp_path / "config.toml").exists()


def test_init_config_is_parseable_by_load_config(tmp_path):
    """config.toml written by 'bb init' can be loaded without error."""
    _invoke_init(tmp_path)
    with patch("bb.config.BB_DIR", tmp_path):
        from bb.config import load_config

        cfg = load_config()

    assert cfg.lms_type == "blackboard_ultra"


def test_init_config_has_default_lms_url(tmp_path):
    """Default URL pre-fill is preserved when user just presses Enter."""
    _invoke_init(tmp_path)
    with patch("bb.config.BB_DIR", tmp_path):
        from bb.config import load_config

        cfg = load_config()

    assert cfg.lms_url == "https://learn.senecapolytechnic.ca"


def test_init_config_has_terminal_notification_provider(tmp_path):
    """Default notification provider is 'terminal'."""
    _invoke_init(tmp_path)
    with patch("bb.config.BB_DIR", tmp_path):
        from bb.config import load_config

        cfg = load_config()

    assert cfg.notification.provider == "terminal"


# ---------------------------------------------------------------------------
# bb.db
# ---------------------------------------------------------------------------


def test_init_creates_database_file(tmp_path):
    """bb.db exists at BB_DIR after 'bb init'."""
    _invoke_init(tmp_path)
    assert (tmp_path / "bb.db").exists()


def test_init_database_contains_deadlines_table(tmp_path):
    """The deadlines table is present in bb.db after 'bb init'."""
    _invoke_init(tmp_path)
    conn = sqlite3.connect(str(tmp_path / "bb.db"))
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='deadlines'"
    )
    result = cursor.fetchone()
    conn.close()

    assert result is not None


def test_init_database_contains_sync_log_table(tmp_path):
    """The sync_log table is present in bb.db after 'bb init'."""
    _invoke_init(tmp_path)
    conn = sqlite3.connect(str(tmp_path / "bb.db"))
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sync_log'"
    )
    result = cursor.fetchone()
    conn.close()

    assert result is not None


def test_init_database_schema_version_is_1(tmp_path):
    """schema_version contains version 1 after 'bb init'."""
    _invoke_init(tmp_path)
    conn = sqlite3.connect(str(tmp_path / "bb.db"))
    cursor = conn.execute("SELECT version FROM schema_version")
    version = cursor.fetchone()[0]
    conn.close()

    assert version == 1


# ---------------------------------------------------------------------------
# Idempotency (re-run)
# ---------------------------------------------------------------------------


def test_init_twice_both_succeed(tmp_path):
    """Running 'bb init' a second time does not error."""
    result1 = _invoke_init(tmp_path)
    result2 = _invoke_init(tmp_path)

    assert result1.exit_code == 0
    assert result2.exit_code == 0


def test_init_twice_config_is_valid(tmp_path):
    """Config is parseable and correct after running 'bb init' twice."""
    _invoke_init(tmp_path)
    _invoke_init(tmp_path)
    with patch("bb.config.BB_DIR", tmp_path):
        from bb.config import load_config

        cfg = load_config()

    assert cfg.lms_type == "blackboard_ultra"


def test_init_twice_database_still_valid(tmp_path):
    """DB schema_version has one row per migration (not duplicated) after two 'bb init' runs."""
    _invoke_init(tmp_path)
    _invoke_init(tmp_path)
    conn = sqlite3.connect(str(tmp_path / "bb.db"))
    count = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
    max_version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    conn.close()

    assert count == 3  # one row per migration version, not duplicated
    assert max_version == 3


# ---------------------------------------------------------------------------
# Output messages
# ---------------------------------------------------------------------------


def test_init_output_mentions_config_saved(tmp_path):
    """Output includes a confirmation that config was saved."""
    result = _invoke_init(tmp_path)
    output_lower = result.output.lower()
    assert "config" in output_lower and (
        "saved" in output_lower or "config.toml" in output_lower
    )


def test_init_output_mentions_database_initialized(tmp_path):
    """Output includes a confirmation that the database was initialized."""
    result = _invoke_init(tmp_path)
    output_lower = result.output.lower()
    assert "database" in output_lower or "bb.db" in output_lower
