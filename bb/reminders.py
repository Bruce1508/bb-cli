"""Deadline reminders: decide which reminders are due, and send each one exactly once.

Runs inside `bb sync` (scheduled by `bb auto-setup`), so no extra scheduler is needed.
Dedup key includes due_at, so a deadline that moves re-arms its reminders automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bb.adapters.base import Deadline
from bb.notify import dispatch_notify

if TYPE_CHECKING:
    from bb.config import NotificationConfig
    from bb.db import Database

# (label, max hours until due, priority) — tightest window first.
# 6h, not 2h: auto-setup syncs every 4h, so a 6h window always contains at least one sync.
WINDOWS: tuple[tuple[str, int, str], ...] = (("6h", 6, "urgent"), ("24h", 24, "high"))
_KEY_TTL_HOURS = 24 * 14  # keys are unique per due_at; TTL only bounds the lookup


@dataclass
class Reminder:
    key: str
    deadline: Deadline
    window: str
    priority: str
    message: str


def _fmt_left(hours: float) -> str:
    if hours < 1:
        return f"{max(1, round(hours * 60))}m"
    return f"{int(hours)}h"


def pending_reminders(deadlines: list[Deadline], now: datetime) -> list[Reminder]:
    """Return at most one reminder per future deadline: the tightest window it falls in."""
    out: list[Reminder] = []
    for d in deadlines:
        hours = (d.due_at - now).total_seconds() / 3600
        if hours <= 0:
            continue
        for label, limit, priority in WINDOWS:
            if hours <= limit:
                out.append(Reminder(
                    key=f"remind:{d.id}:{d.due_at.isoformat()}:{label}",
                    deadline=d,
                    window=label,
                    priority=priority,
                    message=f"{d.course}: {d.title} — due in {_fmt_left(hours)}",
                ))
                break
    return out


def send_reminders(
    db: Database, ncfg: NotificationConfig, now: datetime | None = None
) -> int:
    """Send every pending reminder not sent before. Returns how many were sent."""
    now = now or datetime.now(timezone.utc)
    sent = 0
    for r in pending_reminders(db.get_upcoming_deadlines(days=2), now):
        if db.was_notified_recently(r.key, within_hours=_KEY_TTL_HOURS):
            continue
        dispatch_notify(ncfg, "bb — due soon", r.message, priority=r.priority)
        db.log_notification(r.key)
        sent += 1
    return sent
