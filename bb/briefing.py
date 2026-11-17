"""Plain-text rendering of get_briefing(), for push notifications (no Rich markup)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from bb.notify import dispatch_notify

if TYPE_CHECKING:
    from bb.config import NotificationConfig
    from bb.db import Database


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n != 1 else ''}"


def briefing_text(b: dict, max_items: int = 3) -> str:
    """One-line summary, e.g.
    'Due soon: BTP200 Lab 4 (due in 5h (today)) · 2 unread announcements'."""
    parts: list[str] = []
    urgent = b.get("urgent_deadlines", [])
    if urgent:
        shown = "; ".join(f"{d['course']} {d['title']} ({d['when']})" for d in urgent[:max_items])
        more = f" +{len(urgent) - max_items} more" if len(urgent) > max_items else ""
        parts.append(f"Due soon: {shown}{more}")
    if b.get("later_this_week"):
        parts.append(f"{b['later_this_week']} more this week")
    if b.get("unread_announcements"):
        parts.append(_plural(len(b["unread_announcements"]), "unread announcement"))
    if b.get("recent_changes"):
        parts.append(_plural(len(b["recent_changes"]), "change"))
    return " · ".join(parts) if parts else "Nothing due in the next 48h."


def send_daily_digest(
    db: Database, ncfg: NotificationConfig, now_local: datetime | None = None
) -> bool:
    """Send today's briefing once per local day, on the first sync at/after digest_hour."""
    if not ncfg.daily_digest:
        return False
    now_local = now_local or datetime.now().astimezone()
    if now_local.hour < ncfg.digest_hour:
        return False
    key = f"digest:{now_local.date().isoformat()}"
    if db.was_notified_recently(key, within_hours=36):
        return False
    from bb.tools.queries import get_briefing

    dispatch_notify(ncfg, "bb — today", briefing_text(get_briefing()))
    db.log_notification(key)
    return True
