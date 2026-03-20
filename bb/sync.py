from __future__ import annotations

import httpx

from bb.adapters.base import Announcement, Deadline, GradeItem
from bb.db import Database
from bb.parsers.ical import parse_ical


def sync_ical(ical_url: str, db: Database) -> tuple[int, int]:
    """Fetch iCal feed, parse, upsert deadlines to DB.

    Returns (new_count, updated_count).
    Raises httpx.HTTPStatusError on non-2xx response.
    Raises ICalParseError if the response is not valid iCal data.
    """
    response = httpx.get(ical_url, follow_redirects=True, timeout=30)
    response.raise_for_status()
    deadlines = parse_ical(response.text)
    new = updated = 0
    for d in deadlines:
        if db.upsert_deadline(d):
            new += 1
        else:
            updated += 1
    return new, updated


def sync_stream(adapter: object, db: Database) -> tuple[int, int, int]:
    """Scrape Activity Stream via adapter, upsert all items to DB.

    Returns (deadlines_new, announcements_new, grades_new).
    Raises SessionError if the session is expired or missing.
    """
    items = adapter.fetch_activity_stream()
    d_new = a_new = g_new = 0
    for item in items:
        if isinstance(item, Deadline):
            if db.upsert_deadline(item):
                d_new += 1
        elif isinstance(item, Announcement):
            if db.upsert_announcement(item):
                a_new += 1
        elif isinstance(item, GradeItem):
            if db.upsert_grade(item):
                g_new += 1
    return d_new, a_new, g_new
