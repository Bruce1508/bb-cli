from __future__ import annotations

from bb.notify import ntfy as _ntfy
from bb.notify import terminal as _terminal


def dispatch_notify(provider: str, title: str, body: str, ntfy_topic: str = "") -> None:
    """Route a notification to the configured provider.

    Args:
        provider: One of "terminal", "ntfy". Unknown values are silently ignored.
        title: Short notification title.
        body: Notification body text.
        ntfy_topic: Required when provider is "ntfy"; silently skipped if empty.
    """
    if provider == "terminal":
        _terminal.notify(title, body)
    elif provider == "ntfy":
        _ntfy.notify(ntfy_topic, title, body)
    # telegram / discord: not yet implemented — silent no-op
