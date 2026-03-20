from __future__ import annotations

import time

import httpx

from bb.adapters.base import Announcement, Deadline, GradeItem
from bb.db import Database
from bb.parsers.ical import parse_ical

_ICAL_MAX_RETRIES = 3
_ICAL_BACKOFF_BASE = 2  # seconds; delay = base ** attempt (2, 4, 8)


def sync_ical(ical_url: str, db: Database) -> tuple[int, int]:
    """Fetch iCal feed with retry, parse, upsert deadlines to DB.

    Returns (new_count, updated_count).
    Raises httpx.HTTPStatusError on non-2xx response (after all retries).
    Raises ICalParseError if the response is not valid iCal data.
    """
    last_exc: Exception | None = None
    for attempt in range(_ICAL_MAX_RETRIES):
        try:
            response = httpx.get(ical_url, follow_redirects=True, timeout=30)
            response.raise_for_status()
            break
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            last_exc = exc
            if attempt < _ICAL_MAX_RETRIES - 1:
                time.sleep(_ICAL_BACKOFF_BASE ** (attempt + 1))
    else:
        raise last_exc  # type: ignore[misc]

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

    Saves an HTML snapshot to ~/.bb/snapshots/ when 0 items are scraped
    (useful for debugging selector failures after a BB UI update).
    """
    items = adapter.fetch_activity_stream()

    if not items:
        _save_snapshot(adapter)

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


def sync_grades(adapter: object, db: Database) -> int:
    """Scrape the Grades page via adapter, upsert all grade items to DB.

    Returns grades_new count.
    Raises SessionError if the session is expired or missing.
    """
    items = adapter.fetch_grades()
    new = 0
    for item in items:
        if isinstance(item, GradeItem):
            if db.upsert_grade(item):
                new += 1
    return new


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------


def _save_snapshot(adapter: object) -> None:
    """Save last-fetched page HTML to ~/.bb/snapshots/ for debugging.

    Silent no-op if the adapter doesn't expose a page or saving fails.
    """
    try:
        import bb.config as _config_module

        snapshots_dir = _config_module.BB_DIR / "snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)

        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snapshot_path = snapshots_dir / f"stream_{ts}.html"

        # Adapter exposes _last_page_html set during fetch_activity_stream
        html = getattr(adapter, "_last_page_html", None)
        if html:
            snapshot_path.write_text(html, encoding="utf-8")
    except Exception:
        pass  # snapshot saving is best-effort
