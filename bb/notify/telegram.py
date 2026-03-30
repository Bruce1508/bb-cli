from __future__ import annotations

import httpx


def notify(token: str, chat_id: str, title: str, body: str, priority: str = "default") -> None:
    """Send a push notification via Telegram Bot API.

    Silent no-op on failure — notification failure must never crash sync.

    Args:
        token: Telegram Bot API token (e.g. "123456:ABC-DEF...").
        chat_id: Telegram chat or user ID to send to.
        title: Notification title shown in bold.
        body: Notification body text.
        priority: One of "min", "low", "default", "high", "urgent".
            "high" and "urgent" prefix the title with a red circle indicator.
    """
    if not token or not chat_id:
        return
    try:
        if priority in ("high", "urgent"):
            title = f"🔴 {title}"
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": f"**{title}**\n{body}",
                "parse_mode": "Markdown",
            },
            timeout=10,
        )
    except Exception:
        pass  # notification is non-critical — never propagate
