"""
Tests for bb/notify/terminal.py

Success criteria:
- macOS (darwin): subprocess.run called with ["osascript", "-e", <script>]
- Linux: subprocess.run called with ["notify-send", title, body]
- Other platforms: subprocess.run NOT called (silent no-op)
- notify() never raises, even if subprocess.run raises
- Title and body appear correctly in the command arguments
"""
from unittest.mock import MagicMock, call, patch

import pytest

from bb.notify.terminal import notify


# ---------------------------------------------------------------------------
# macOS
# ---------------------------------------------------------------------------


def test_macos_calls_osascript():
    with patch("sys.platform", "darwin"), patch("subprocess.run") as mock_run:
        notify("bb", "3 new deadlines synced")
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "osascript"
    assert args[1] == "-e"


def test_macos_command_contains_title():
    with patch("sys.platform", "darwin"), patch("subprocess.run") as mock_run:
        notify("My Title", "Some body")
    script = mock_run.call_args[0][0][2]
    assert "My Title" in script


def test_macos_command_contains_body():
    with patch("sys.platform", "darwin"), patch("subprocess.run") as mock_run:
        notify("My Title", "Some body text")
    script = mock_run.call_args[0][0][2]
    assert "Some body text" in script


def test_macos_uses_check_false():
    """check=False ensures notification failure never raises CalledProcessError."""
    with patch("sys.platform", "darwin"), patch("subprocess.run") as mock_run:
        notify("bb", "body")
    _, kwargs = mock_run.call_args
    assert kwargs.get("check") is False


def test_macos_args_passed_as_list_not_string():
    """Args must be a list to prevent shell injection."""
    with patch("sys.platform", "darwin"), patch("subprocess.run") as mock_run:
        notify("bb", "body")
    args = mock_run.call_args[0][0]
    assert isinstance(args, list)


# ---------------------------------------------------------------------------
# Linux
# ---------------------------------------------------------------------------


def test_linux_calls_notify_send():
    with patch("sys.platform", "linux"), patch("subprocess.run") as mock_run:
        notify("bb", "3 new deadlines synced")
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "notify-send"


def test_linux_passes_title_and_body_as_separate_args():
    """notify-send takes title and body as separate positional args."""
    with patch("sys.platform", "linux"), patch("subprocess.run") as mock_run:
        notify("My Title", "My Body")
    args = mock_run.call_args[0][0]
    assert "My Title" in args
    assert "My Body" in args


def test_linux_uses_check_false():
    with patch("sys.platform", "linux"), patch("subprocess.run") as mock_run:
        notify("bb", "body")
    _, kwargs = mock_run.call_args
    assert kwargs.get("check") is False


# ---------------------------------------------------------------------------
# Other platforms — silent no-op
# ---------------------------------------------------------------------------


def test_windows_does_not_call_subprocess():
    with patch("sys.platform", "win32"), patch("subprocess.run") as mock_run:
        notify("bb", "body")
    mock_run.assert_not_called()


def test_unknown_platform_does_not_call_subprocess():
    with patch("sys.platform", "freebsd"), patch("subprocess.run") as mock_run:
        notify("bb", "body")
    mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Never raises
# ---------------------------------------------------------------------------


def test_notify_does_not_raise_when_subprocess_raises():
    """notification failure must never propagate."""
    with patch("sys.platform", "darwin"), patch("subprocess.run", side_effect=OSError("not found")):
        notify("bb", "body")  # must not raise


def test_notify_does_not_raise_on_linux_failure():
    with patch("sys.platform", "linux"), patch("subprocess.run", side_effect=FileNotFoundError):
        notify("bb", "body")  # must not raise


def test_notify_returns_none():
    with patch("sys.platform", "darwin"), patch("subprocess.run"):
        result = notify("bb", "body")
    assert result is None
