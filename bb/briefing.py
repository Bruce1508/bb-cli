"""Plain-text rendering of get_briefing(), for push notifications (no Rich markup)."""

from __future__ import annotations


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n != 1 else ''}"


def briefing_text(b: dict, max_items: int = 3) -> str:
    """One-line summary, e.g. 'Due ≤48h: BTP200 Lab 4 (due in 5h) · 2 unread announcements'."""
    parts: list[str] = []
    urgent = b.get("urgent_deadlines", [])
    if urgent:
        shown = "; ".join(f"{d['course']} {d['title']} ({d['when']})" for d in urgent[:max_items])
        more = f" +{len(urgent) - max_items} more" if len(urgent) > max_items else ""
        parts.append(f"Due ≤48h: {shown}{more}")
    if b.get("later_this_week"):
        parts.append(f"{b['later_this_week']} more this week")
    if b.get("unread_announcements"):
        parts.append(_plural(len(b["unread_announcements"]), "unread announcement"))
    if b.get("recent_changes"):
        parts.append(_plural(len(b["recent_changes"]), "change"))
    return " · ".join(parts) if parts else "Nothing due in the next 48h."
