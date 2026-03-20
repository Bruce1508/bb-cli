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


def install_auto_sync(interval_hours: int = 4) -> tuple[str, str]:
    """Install OS-native scheduler to run bb sync every interval_hours.

    Returns (platform, detail_message).
    Raises RuntimeError on unsupported platform.
    """
    plat = _platform()
    if plat == "macos":
        return "macOS", _install_macos(interval_hours)
    elif plat == "linux":
        return "Linux", _install_linux(interval_hours)
    else:
        raise RuntimeError(
            "Auto-setup is not supported on Windows. Run `bb sync` manually or use Task Scheduler."
        )


def uninstall_auto_sync() -> tuple[str, str]:
    """Remove the OS-native scheduler installed by install_auto_sync().

    Returns (platform, detail_message).
    Raises RuntimeError on unsupported platform.
    """
    plat = _platform()
    if plat == "macos":
        return "macOS", _uninstall_macos()
    elif plat == "linux":
        return "Linux", _uninstall_linux()
    else:
        raise RuntimeError("Auto-setup is not supported on Windows.")


# ------------------------------------------------------------------
# macOS — launchd
# ------------------------------------------------------------------

_PLIST_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
{args}
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


def _install_macos(interval_hours: int) -> str:
    """Write plist and bootstrap via launchctl. Returns detail message."""
    bb_args = _bb_executable_args()
    args_xml = "\n".join(f"        <string>{a}</string>" for a in bb_args + ["sync"])

    plist_content = _PLIST_TEMPLATE.format(
        label=PLIST_LABEL,
        args=args_xml,
        interval_seconds=interval_hours * 3600,
        log_path=str(LOG_PATH),
    )

    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(plist_content, encoding="utf-8")

    uid = os.getuid()
    domain = f"gui/{uid}"

    # Bootout first — idempotent, ignore errors (job may not be loaded yet)
    subprocess.run(
        ["launchctl", "bootout", domain, str(PLIST_PATH)],
        capture_output=True,
    )

    # Bootstrap (modern API — replaces deprecated launchctl load)
    result = subprocess.run(
        ["launchctl", "bootstrap", domain, str(PLIST_PATH)],
        capture_output=True,
    )

    if result.returncode != 0:
        return (
            f"Plist written to {PLIST_PATH}\n"
            f"  [yellow]⚠ Could not load automatically "
            f"(launchctl exit {result.returncode}).[/yellow]\n"
            f"  Run manually: launchctl bootstrap {domain} {PLIST_PATH}"
        )

    # Verify the service is registered
    verify = subprocess.run(
        ["launchctl", "print", f"{domain}/{PLIST_LABEL}"],
        capture_output=True,
    )
    if verify.returncode != 0:
        return (
            f"Plist written to {PLIST_PATH}\n"
            f"  [yellow]⚠ Service registered but not yet visible "
            f"(will activate on next login).[/yellow]"
        )

    return (
        f"Created {PLIST_PATH}\n"
        f"[green]✔[/green] Auto-sync enabled: every {interval_hours} hours\n"
        f"  Logs: {LOG_PATH}\n"
        f"  Run `bb auto-setup --disable` to stop"
    )


def _uninstall_macos() -> str:
    """Bootout and delete plist. Returns detail message."""
    if not PLIST_PATH.exists():
        return "Auto-sync is not currently installed."

    uid = os.getuid()
    domain = f"gui/{uid}"

    result = subprocess.run(
        ["launchctl", "bootout", domain, str(PLIST_PATH)],
        capture_output=True,
    )

    if result.returncode == 0:
        unload_msg = f"[green]✔[/green] Unloaded {PLIST_LABEL}"
    else:
        unload_msg = "Plist removed (scheduler was not active)"

    PLIST_PATH.unlink()
    return f"{unload_msg}\n[green]✔[/green] Deleted {PLIST_PATH}\n  Auto-sync disabled."


# ------------------------------------------------------------------
# Linux — crontab
# ------------------------------------------------------------------


def _install_linux(interval_hours: int) -> str:
    """Inject crontab entry with marker. Returns detail message."""
    bb_args = _bb_executable_args()
    bb_cmd = " ".join(bb_args + ["sync"])
    log_path = str(LOG_PATH)
    schedule = f"0 */{interval_hours} * * *"
    new_entry = f"{schedule} {bb_cmd} >> {log_path} 2>&1  {CRON_MARKER}"

    try:
        current = subprocess.check_output(["crontab", "-l"], stderr=subprocess.DEVNULL).decode()
    except subprocess.CalledProcessError:
        current = ""

    lines = [ln for ln in current.splitlines() if CRON_MARKER not in ln]
    lines.append(new_entry)

    subprocess.run(
        ["crontab", "-"],
        input=("\n".join(lines) + "\n").encode(),
        check=False,
    )

    return (
        f"[green]✔[/green] Auto-sync enabled: every {interval_hours} hours\n"
        f"  Logs: {log_path}\n"
        f"  Run `bb auto-setup --disable` to stop"
    )


def _uninstall_linux() -> str:
    """Remove bb-cli crontab entry. Returns detail message."""
    try:
        current = subprocess.check_output(["crontab", "-l"], stderr=subprocess.DEVNULL).decode()
    except subprocess.CalledProcessError:
        return "Auto-sync is not currently installed."

    if CRON_MARKER not in current:
        return "Auto-sync is not currently installed."

    lines = [ln for ln in current.splitlines() if CRON_MARKER not in ln]
    subprocess.run(
        ["crontab", "-"],
        input=("\n".join(lines) + "\n").encode(),
        check=False,
    )
    return "[green]✔[/green] Auto-sync disabled."


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


def _bb_executable_args() -> list[str]:
    """Return the ProgramArguments prefix to invoke bb.

    Priority:
    1. shutil.which("bb") — works when bb is installed in PATH
       os.path.abspath() normalises relative venv paths to stable absolute paths.
    2. Fallback: [sys.executable, "-m", "bb"] — works for editable installs.
    """
    bb = shutil.which("bb")
    if bb:
        return [os.path.abspath(bb)]
    return [sys.executable, "-m", "bb"]
