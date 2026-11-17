from __future__ import annotations

import subprocess
import sys


def notify(title: str, body: str) -> None:
    """Send an OS-native desktop notification.

    Silent no-op on unsupported platforms — notification failure must
    never crash the sync process.
    """
    try:
        if sys.platform == "darwin":
            subprocess.run(
                [
                    "osascript",
                    "-e", "on run argv",
                    "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
                    "-e", "end run",
                    "--", title, body,
                ],
                check=False,
            )
        elif sys.platform.startswith("linux"):
            subprocess.run(["notify-send", title, body], check=False)
        # Other platforms: silent no-op
    except Exception:
        pass  # notification is non-critical — never propagate
