"""
Tests for bb/auto_setup.py — pure helper functions

Strategy:
- generate_plist and generate_crontab_line are pure functions — no mocks needed
- install_macos / uninstall_macos patched with tmp_path + mock subprocess
- install_linux / uninstall_linux patched subprocess for crontab read/write

Success criteria:
- generate_plist: valid XML, label "com.bb-cli.sync", interval in seconds, bb exe + "sync" present
- generate_crontab_line: correct cron expression per interval, contains bb exe + sync, /dev/null, bb-cli marker
- install_macos: writes plist file, calls launchctl load with plist path
- uninstall_macos: calls launchctl unload, removes file; no-op when file absent
- install_linux: reads existing crontab, appends bb-cli line, preserves other entries
- uninstall_linux: removes bb-cli line, preserves other entries
"""
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bb.auto_setup import (
    PLIST_LABEL,
    PLIST_PATH,
    generate_crontab_line,
    generate_plist,
    install_linux,
    install_macos,
    uninstall_linux,
    uninstall_macos,
)

BB_EXE = "/usr/local/bin/bb"


# ---------------------------------------------------------------------------
# generate_plist — pure function
# ---------------------------------------------------------------------------


def test_generate_plist_returns_string():
    assert isinstance(generate_plist(4, BB_EXE), str)


def test_generate_plist_is_valid_xml():
    ET.fromstring(generate_plist(4, BB_EXE))  # raises ParseError if malformed


def test_generate_plist_contains_correct_label():
    assert PLIST_LABEL in generate_plist(4, BB_EXE)
    assert "com.bb-cli.sync" in generate_plist(4, BB_EXE)


def test_generate_plist_contains_bb_exe():
    assert BB_EXE in generate_plist(4, BB_EXE)


def test_generate_plist_contains_sync_argument():
    """ProgramArguments must include the 'sync' subcommand."""
    assert "sync" in generate_plist(4, BB_EXE)


def test_generate_plist_4h_encodes_14400_seconds():
    assert "14400" in generate_plist(4, BB_EXE)


def test_generate_plist_1h_encodes_3600_seconds():
    assert "3600" in generate_plist(1, BB_EXE)


def test_generate_plist_arbitrary_interval_correct():
    result = generate_plist(6, BB_EXE)
    assert str(6 * 3600) in result


def test_generate_plist_different_intervals_produce_different_content():
    assert generate_plist(4, BB_EXE) != generate_plist(8, BB_EXE)


def test_generate_plist_default_label_constant():
    assert PLIST_LABEL == "com.bb-cli.sync"


def test_generate_plist_default_path_is_launch_agents():
    assert "LaunchAgents" in str(PLIST_PATH)
    assert "com.bb-cli.sync.plist" in str(PLIST_PATH)


# ---------------------------------------------------------------------------
# generate_crontab_line — pure function
# ---------------------------------------------------------------------------


def test_generate_crontab_line_returns_string():
    assert isinstance(generate_crontab_line(4, BB_EXE), str)


def test_generate_crontab_line_contains_bb_exe():
    assert BB_EXE in generate_crontab_line(4, BB_EXE)


def test_generate_crontab_line_contains_sync():
    assert "sync" in generate_crontab_line(4, BB_EXE)


def test_generate_crontab_line_4h_uses_every_4_hours():
    """4-hour interval → '*/4' in the hours field."""
    assert "*/4" in generate_crontab_line(4, BB_EXE)


def test_generate_crontab_line_1h_uses_every_hour():
    line = generate_crontab_line(1, BB_EXE)
    assert "*/1" in line or ("* * * *" in line)


def test_generate_crontab_line_suppresses_output():
    """Cron job must run silently — no terminal window spam."""
    assert "/dev/null" in generate_crontab_line(4, BB_EXE)


def test_generate_crontab_line_has_bb_cli_marker():
    """Marker comment lets uninstall_linux find and remove the line safely."""
    assert "bb-cli" in generate_crontab_line(4, BB_EXE)


def test_generate_crontab_line_is_single_line():
    result = generate_crontab_line(4, BB_EXE)
    assert "\n" not in result.strip()


# ---------------------------------------------------------------------------
# install_macos
# ---------------------------------------------------------------------------


def test_install_macos_writes_plist_file(tmp_path):
    plist_path = tmp_path / "com.bb-cli.sync.plist"
    with patch("subprocess.run"):
        install_macos(4, BB_EXE, plist_path=plist_path)
    assert plist_path.exists()


def test_install_macos_plist_content_is_valid_xml(tmp_path):
    plist_path = tmp_path / "com.bb-cli.sync.plist"
    with patch("subprocess.run"):
        install_macos(4, BB_EXE, plist_path=plist_path)
    ET.fromstring(plist_path.read_text())


def test_install_macos_calls_launchctl_load(tmp_path):
    plist_path = tmp_path / "com.bb-cli.sync.plist"
    with patch("subprocess.run") as mock_run:
        install_macos(4, BB_EXE, plist_path=plist_path)
    args = mock_run.call_args[0][0]
    assert "launchctl" in args
    assert "load" in args


def test_install_macos_launchctl_load_passes_plist_path(tmp_path):
    plist_path = tmp_path / "com.bb-cli.sync.plist"
    with patch("subprocess.run") as mock_run:
        install_macos(4, BB_EXE, plist_path=plist_path)
    args = mock_run.call_args[0][0]
    assert str(plist_path) in args


def test_install_macos_creates_parent_dir_if_missing(tmp_path):
    nested = tmp_path / "LaunchAgents"
    plist_path = nested / "com.bb-cli.sync.plist"
    with patch("subprocess.run"):
        install_macos(4, BB_EXE, plist_path=plist_path)
    assert plist_path.exists()


# ---------------------------------------------------------------------------
# uninstall_macos
# ---------------------------------------------------------------------------


def test_uninstall_macos_removes_plist_file(tmp_path):
    plist_path = tmp_path / "com.bb-cli.sync.plist"
    plist_path.write_text("<plist/>")
    with patch("subprocess.run"):
        uninstall_macos(plist_path=plist_path)
    assert not plist_path.exists()


def test_uninstall_macos_calls_launchctl_unload(tmp_path):
    plist_path = tmp_path / "com.bb-cli.sync.plist"
    plist_path.write_text("<plist/>")
    with patch("subprocess.run") as mock_run:
        uninstall_macos(plist_path=plist_path)
    args = mock_run.call_args[0][0]
    assert "launchctl" in args
    assert "unload" in args


def test_uninstall_macos_is_noop_when_file_missing(tmp_path):
    plist_path = tmp_path / "com.bb-cli.sync.plist"
    with patch("subprocess.run") as mock_run:
        uninstall_macos(plist_path=plist_path)  # must not raise
    mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# install_linux / uninstall_linux
# ---------------------------------------------------------------------------


def _make_crontab_subprocess(existing_crontab: str = ""):
    """Return a side_effect function that simulates crontab -l and crontab -."""

    def side_effect(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        if "-l" in cmd:
            result.stdout = existing_crontab
        return result

    return side_effect


def test_install_linux_calls_crontab(tmp_path):
    with patch("subprocess.run", side_effect=_make_crontab_subprocess()) as mock_run:
        install_linux(4, BB_EXE)
    assert any("crontab" in str(c) for c in mock_run.call_args_list)


def test_install_linux_writes_new_entry():
    """Written crontab should contain the bb-cli sync line."""
    with patch("subprocess.run", side_effect=_make_crontab_subprocess()) as mock_run:
        install_linux(4, BB_EXE)
    write_call = mock_run.call_args_list[-1]
    written = write_call[1].get("input", "")
    assert BB_EXE in written and "sync" in written


def test_install_linux_preserves_existing_entries():
    """Existing crontab lines must survive the bb-cli install."""
    existing = "30 8 * * * /usr/bin/my-backup\n"
    with patch("subprocess.run", side_effect=_make_crontab_subprocess(existing)) as mock_run:
        install_linux(4, BB_EXE)
    write_call = mock_run.call_args_list[-1]
    written = write_call[1].get("input", "")
    assert "/usr/bin/my-backup" in written


def test_uninstall_linux_removes_bb_cli_line():
    """uninstall_linux must remove the bb-cli line and nothing else."""
    bb_line = f"0 */4 * * * {BB_EXE} sync >/dev/null 2>&1  # bb-cli auto-sync\n"
    crontab = f"30 8 * * * /usr/bin/my-backup\n{bb_line}"
    with patch("subprocess.run", side_effect=_make_crontab_subprocess(crontab)) as mock_run:
        uninstall_linux(BB_EXE)
    write_call = mock_run.call_args_list[-1]
    written = write_call[1].get("input", "")
    assert "bb-cli auto-sync" not in written
    assert "/usr/bin/my-backup" in written


def test_uninstall_linux_noop_when_no_entry():
    """If bb-cli was never installed, uninstall should not crash."""
    crontab = "30 8 * * * /usr/bin/my-backup\n"
    with patch("subprocess.run", side_effect=_make_crontab_subprocess(crontab)):
        uninstall_linux(BB_EXE)  # must not raise
