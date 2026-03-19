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
                ["osascript", "-e", f'display notification "{body}" with title "{title}"'],
                check=False,
            )
        elif sys.platform.startswith("linux"):
            subprocess.run(["notify-send", title, body], check=False)
        # Other platforms: silent no-op
    except Exception:
        pass  # notification is non-critical — never propagate
