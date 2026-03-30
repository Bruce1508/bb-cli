from __future__ import annotations

import httpx


def notify(webhook_url: str, title: str, body: str, priority: str = "default") -> None:
    """Send a push notification via Discord webhook.

    Silent no-op on failure — notification failure must never crash sync.

    Args:
        webhook_url: Full Discord webhook URL
            (e.g. "https://discord.com/api/webhooks/...").
        title: Notification title shown in bold.
        body: Notification body text.
        priority: One of "min", "low", "default", "high", "urgent".
            "high" and "urgent" prefix the title with a red circle indicator.
    """
    if not webhook_url:
        return
    try:
        if priority in ("high", "urgent"):
            title = f"🔴 {title}"
        httpx.post(
            webhook_url,
            json={"content": f"**{title}**\n{body}"},
            timeout=10,
        )
    except Exception:
        pass  # notification is non-critical — never propagate
