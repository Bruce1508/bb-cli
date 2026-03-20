from __future__ import annotations

import httpx

NTFY_BASE_URL = "https://ntfy.sh"


def notify(topic: str, title: str, body: str, priority: str = "default") -> None:
    """Send a push notification via ntfy.sh.

    Silent no-op on failure — notification failure must never crash sync.

    Args:
        topic: ntfy.sh topic name (e.g. "my-bb-alerts").
        title: Notification title shown in bold.
        body: Notification body text.
        priority: One of "min", "low", "default", "high", "urgent".
    """
    if not topic:
        return
    try:
        httpx.post(
            f"{NTFY_BASE_URL}/{topic}",
            content=body.encode(),
            headers={
                "Title": title,
                "Priority": priority,
            },
            timeout=10,
        )
    except Exception:
        pass  # notification is non-critical — never propagate
