from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# macOS launchd constants
PLIST_LABEL = "com.bb-cli.sync"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"

# Linux crontab marker — used to find and remove the entry
CRON_MARKER = "# bb-cli auto-sync"

# Log file for scheduled runs
LOG_PATH = Path.home() / ".bb" / "sync.log"


# ------------------------------------------------------------------
# Pure helper functions (no side effects — easy to unit test)
# ------------------------------------------------------------------


def generate_plist(interval_hours: int, bb_exe: str) -> str:
    """Return a launchd plist XML string for the given interval and executable."""
    interval_seconds = interval_hours * 3600
    log_path = str(LOG_PATH)
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{bb_exe}</string>
        <string>sync</string>
    </array>
    <key>StartInterval</key>
    <integer>{interval_seconds}</integer>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""


def generate_crontab_line(interval_hours: int, bb_exe: str) -> str:
    """Return a single crontab line for the given interval and executable."""
    schedule = f"0 */{interval_hours} * * *"
    log_path = str(LOG_PATH)
    return f"{schedule} {bb_exe} sync >> {log_path} 2>&1 >/dev/null  {CRON_MARKER}"


# ------------------------------------------------------------------
# macOS — launchd
# ------------------------------------------------------------------


def install_macos(
    interval_hours: int,
    bb_exe: str,
    *,
    plist_path: Path = PLIST_PATH,
) -> str:
    """Write plist and load via launchctl. Returns detail message."""
    plist_content = generate_plist(interval_hours, bb_exe)

    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist_content, encoding="utf-8")

    result = subprocess.run(
        ["launchctl", "load", str(plist_path)],
        capture_output=True,
    )

    if result.returncode != 0:
        return (
            f"Plist written to {plist_path}\n"
            f"  Could not load automatically "
            f"(launchctl exit {result.returncode}).\n"
            f"  Run manually: launchctl load {plist_path}"
        )

    return (
        f"Created {plist_path}\n"
        f"Auto-sync enabled: every {interval_hours} hours\n"
        f"  Logs: {LOG_PATH}\n"
        f"  Run `bb auto-setup --disable` to stop"
    )


def uninstall_macos(*, plist_path: Path = PLIST_PATH) -> str:
    """Unload and delete plist. Returns detail message."""
    if not plist_path.exists():
        return "Auto-sync is not currently installed."

    subprocess.run(
        ["launchctl", "unload", str(plist_path)],
        capture_output=True,
    )

    plist_path.unlink()
    return f"Unloaded {PLIST_LABEL}\nDeleted {plist_path}\n  Auto-sync disabled."


# ------------------------------------------------------------------
# Linux — crontab
# ------------------------------------------------------------------


def install_linux(interval_hours: int, bb_exe: str) -> str:
    """Inject crontab entry with marker. Returns detail message."""
    new_entry = generate_crontab_line(interval_hours, bb_exe)

    result = subprocess.run(
        ["crontab", "-l"],
        capture_output=True,
        text=True,
    )
    current = result.stdout or ""

    lines = [ln for ln in current.splitlines() if CRON_MARKER not in ln]
    lines.append(new_entry)

    subprocess.run(
        ["crontab", "-"],
        input="\n".join(lines) + "\n",
        text=True,
        check=False,
    )

    return (
        f"Auto-sync enabled: every {interval_hours} hours\n"
        f"  Logs: {LOG_PATH}\n"
        f"  Run `bb auto-setup --disable` to stop"
    )


def uninstall_linux(bb_exe: str) -> str:
    """Remove bb-cli crontab entry. Returns detail message."""
    result = subprocess.run(
        ["crontab", "-l"],
        capture_output=True,
        text=True,
    )
    current = result.stdout or ""

    if CRON_MARKER not in current:
        return "Auto-sync is not currently installed."

    lines = [ln for ln in current.splitlines() if CRON_MARKER not in ln]
    subprocess.run(
        ["crontab", "-"],
        input="\n".join(lines) + "\n",
        text=True,
        check=False,
    )
    return "Auto-sync disabled."


# ------------------------------------------------------------------
# Shared helpers
# ------------------------------------------------------------------


def _platform() -> str:
    """Return 'macos', 'linux', or 'unsupported'."""
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return "unsupported"


def _bb_executable() -> str:
    """Return the absolute path to the bb executable.

    Priority:
    1. shutil.which("bb") — works when bb is installed in PATH.
       os.path.abspath() normalises relative venv paths to stable absolute paths.
    2. Fallback: sys.executable + " -m bb" — works for editable installs.
    """
    bb = shutil.which("bb")
    if bb:
        return os.path.abspath(bb)
    # Fallback for editable installs without bb in PATH.
    # Note: this works for crontab (shell context); launchd requires bb in PATH.
    return f"{sys.executable} -m bb"


# ------------------------------------------------------------------
# High-level API used by cli.py
# ------------------------------------------------------------------


def install_auto_sync(interval_hours: int = 4) -> tuple[str, str]:
    """Install OS-native scheduler to run bb sync every interval_hours.

    Returns (platform_label, detail_message).
    Raises RuntimeError on unsupported platform or when bb is not in PATH on macOS.
    """
    plat = _platform()
    if plat == "macos":
        # launchd uses execvp (no shell) — bb must be a real binary in PATH.
        bb = shutil.which("bb")
        if not bb:
            raise RuntimeError(
                "Cannot find `bb` in PATH. Install bb-cli globally "
                "(`uv tool install bb-cli`) before setting up auto-sync."
            )
        return "macOS", install_macos(interval_hours, os.path.abspath(bb))
    elif plat == "linux":
        return "Linux", install_linux(interval_hours, _bb_executable())
    else:
        raise RuntimeError(
            "Auto-setup is not supported on Windows. Run `bb sync` manually or use Task Scheduler."
        )


def uninstall_auto_sync() -> tuple[str, str]:
    """Remove the OS-native scheduler installed by install_auto_sync().

    Returns (platform_label, detail_message).
    Raises RuntimeError on unsupported platform.
    """
    plat = _platform()
    if plat == "macos":
        return "macOS", uninstall_macos()
    elif plat == "linux":
        return "Linux", uninstall_linux(_bb_executable())
    else:
        raise RuntimeError("Auto-setup is not supported on Windows.")
