from __future__ import annotations

from typing import TYPE_CHECKING

from bb.notify import discord as _discord
from bb.notify import ntfy as _ntfy
from bb.notify import telegram as _telegram
from bb.notify import terminal as _terminal

if TYPE_CHECKING:
    from bb.config import NotificationConfig


def dispatch_notify(
    ncfg: NotificationConfig, title: str, body: str, priority: str = "default"
) -> None:
    """Send one notification through the provider configured in `ncfg`.

    Never raises — every provider swallows its own network errors.

    Args:
        ncfg: The [notification] section of the user's config.
        title: Short notification title.
        body: Notification body text.
        priority: "min" | "low" | "default" | "high" | "urgent". Terminal ignores it.
    """
    provider = ncfg.provider
    if provider == "terminal":
        _terminal.notify(title, body)
    elif provider == "ntfy":
        _ntfy.notify(ncfg.ntfy_topic, title, body, priority)
    elif provider == "telegram":
        _telegram.notify(ncfg.telegram_token, ncfg.telegram_chat_id, title, body, priority)
    elif provider == "discord":
        _discord.notify(ncfg.discord_webhook, title, body, priority)
