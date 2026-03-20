"""
Tests for `bb auto-setup` command in bb/cli.py

Strategy:
- Patch sys.platform for OS detection
- Patch bb.auto_setup.install_*/uninstall_* to avoid touching the real OS scheduler
- Patch bb.cli.load_config to control sync_interval_hours

Success criteria:
- macOS: prints "macOS" detected, calls install_macos, exits 0
- Linux: prints "Linux" detected, calls install_linux, exits 0
- Unsupported platform: prints unsupported message
- --disable on macOS: calls uninstall_macos, prints disabled/removed/stopped
- --disable on Linux: calls uninstall_linux
- interval_hours is read from config and passed to install_*
- bb auto-setup --disable on unsupported: prints unsupported
"""
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from bb.cli import app
from bb.config import BBConfig, NotificationConfig

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(interval_hours: int = 4) -> BBConfig:
    return BBConfig(
        lms_type="blackboard_ultra",
        lms_url="https://learn.example.com",
        notification=NotificationConfig(provider="terminal"),
        sync_interval_hours=interval_hours,
    )


def _invoke(tmp_path, *args, platform: str = "darwin", interval: int = 4):
    with (
        patch("sys.platform", platform),
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.load_config", return_value=_make_config(interval)),
        patch("bb.auto_setup.install_macos"),
        patch("bb.auto_setup.install_linux"),
        patch("bb.auto_setup.uninstall_macos"),
        patch("bb.auto_setup.uninstall_linux"),
    ):
        return runner.invoke(app, ["auto-setup", *args])


# ---------------------------------------------------------------------------
# Exit code
# ---------------------------------------------------------------------------


def test_auto_setup_exits_zero_on_macos(tmp_path):
    result = _invoke(tmp_path, platform="darwin")
    assert result.exit_code == 0, result.output


def test_auto_setup_exits_zero_on_linux(tmp_path):
    result = _invoke(tmp_path, platform="linux")
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# Platform detection output
# ---------------------------------------------------------------------------


def test_auto_setup_prints_macos_when_darwin(tmp_path):
    result = _invoke(tmp_path, platform="darwin")
    assert "macOS" in result.output


def test_auto_setup_prints_linux_when_linux(tmp_path):
    result = _invoke(tmp_path, platform="linux")
    assert "Linux" in result.output


def test_auto_setup_prints_unsupported_on_windows(tmp_path):
    result = _invoke(tmp_path, platform="win32")
    out = result.output.lower()
    assert "not supported" in out or "unsupported" in out or "windows" in out


def test_auto_setup_prints_interval_in_output(tmp_path):
    result = _invoke(tmp_path, platform="darwin", interval=4)
    assert "4" in result.output


# ---------------------------------------------------------------------------
# install_* is called with correct arguments
# ---------------------------------------------------------------------------


def test_auto_setup_macos_calls_install_macos(tmp_path):
    with (
        patch("sys.platform", "darwin"),
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.load_config", return_value=_make_config(4)),
        patch("bb.auto_setup.install_macos") as mock_install,
        patch("bb.auto_setup.install_linux"),
        patch("bb.auto_setup.uninstall_macos"),
        patch("bb.auto_setup.uninstall_linux"),
    ):
        runner.invoke(app, ["auto-setup"])
    mock_install.assert_called_once()


def test_auto_setup_linux_calls_install_linux(tmp_path):
    with (
        patch("sys.platform", "linux"),
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.load_config", return_value=_make_config(4)),
        patch("bb.auto_setup.install_macos"),
        patch("bb.auto_setup.install_linux") as mock_install,
        patch("bb.auto_setup.uninstall_macos"),
        patch("bb.auto_setup.uninstall_linux"),
    ):
        runner.invoke(app, ["auto-setup"])
    mock_install.assert_called_once()


def test_auto_setup_passes_interval_from_config_to_install_macos(tmp_path):
    """install_macos must receive the interval from config, not a hardcoded value."""
    with (
        patch("sys.platform", "darwin"),
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.load_config", return_value=_make_config(interval_hours=6)),
        patch("bb.auto_setup.install_macos") as mock_install,
        patch("bb.auto_setup.install_linux"),
        patch("bb.auto_setup.uninstall_macos"),
        patch("bb.auto_setup.uninstall_linux"),
    ):
        runner.invoke(app, ["auto-setup"])
    call_args = mock_install.call_args
    passed_interval = call_args[0][0] if call_args[0] else call_args[1].get("interval_hours")
    assert passed_interval == 6


def test_auto_setup_passes_interval_to_install_linux(tmp_path):
    with (
        patch("sys.platform", "linux"),
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.load_config", return_value=_make_config(interval_hours=8)),
        patch("bb.auto_setup.install_macos"),
        patch("bb.auto_setup.install_linux") as mock_install,
        patch("bb.auto_setup.uninstall_macos"),
        patch("bb.auto_setup.uninstall_linux"),
    ):
        runner.invoke(app, ["auto-setup"])
    call_args = mock_install.call_args
    passed_interval = call_args[0][0] if call_args[0] else call_args[1].get("interval_hours")
    assert passed_interval == 8


# ---------------------------------------------------------------------------
# --disable flag
# ---------------------------------------------------------------------------


def test_auto_setup_disable_macos_calls_uninstall_macos(tmp_path):
    with (
        patch("sys.platform", "darwin"),
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.load_config", return_value=_make_config()),
        patch("bb.auto_setup.install_macos"),
        patch("bb.auto_setup.install_linux"),
        patch("bb.auto_setup.uninstall_macos") as mock_uninstall,
        patch("bb.auto_setup.uninstall_linux"),
    ):
        runner.invoke(app, ["auto-setup", "--disable"])
    mock_uninstall.assert_called_once()


def test_auto_setup_disable_linux_calls_uninstall_linux(tmp_path):
    with (
        patch("sys.platform", "linux"),
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.load_config", return_value=_make_config()),
        patch("bb.auto_setup.install_macos"),
        patch("bb.auto_setup.install_linux"),
        patch("bb.auto_setup.uninstall_macos"),
        patch("bb.auto_setup.uninstall_linux") as mock_uninstall,
    ):
        runner.invoke(app, ["auto-setup", "--disable"])
    mock_uninstall.assert_called_once()


def test_auto_setup_disable_prints_confirmation(tmp_path):
    result = _invoke(tmp_path, "--disable", platform="darwin")
    out = result.output.lower()
    assert "disable" in out or "removed" in out or "stopped" in out or "unloaded" in out


def test_auto_setup_disable_does_not_call_install(tmp_path):
    with (
        patch("sys.platform", "darwin"),
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.load_config", return_value=_make_config()),
        patch("bb.auto_setup.install_macos") as mock_install,
        patch("bb.auto_setup.install_linux"),
        patch("bb.auto_setup.uninstall_macos"),
        patch("bb.auto_setup.uninstall_linux"),
    ):
        runner.invoke(app, ["auto-setup", "--disable"])
    mock_install.assert_not_called()
