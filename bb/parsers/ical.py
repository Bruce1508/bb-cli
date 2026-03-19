from __future__ import annotations

from datetime import datetime, timezone

import icalendar

from bb.adapters.base import Deadline
from bb.hash import content_hash


class ICalParseError(ValueError):
    """Raised when the .ics content cannot be parsed."""


def parse_ical(text: str) -> list[Deadline]:
    """Parse raw .ics string into a list of Deadlines. No I/O.

    Raises ICalParseError if the text is not valid iCal data.
    Skips events missing DTSTART or with empty/missing SUMMARY.
    """
    try:
        cal = icalendar.Calendar.from_ical(text)
    except Exception as exc:
        raise ICalParseError(str(exc)) from exc

    deadlines: list[Deadline] = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        # --- SUMMARY ---
        raw_summary = str(component.get("SUMMARY", "")).strip()
        if not raw_summary:
            continue

        course, title = _extract_course_and_title(raw_summary)

        # --- DTSTART ---
        dtstart = component.get("DTSTART")
        if dtstart is None:
            continue

        due_at = _normalise_to_utc(dtstart.dt)

        # --- ID ---
        deadline_id = content_hash(course, title, due_at.isoformat())

        deadlines.append(
            Deadline(
                id=deadline_id,
                course=course,
                title=title,
                due_at=due_at,
                source="ical",
            )
        )

    return deadlines


def _extract_course_and_title(summary: str) -> tuple[str, str]:
    """Split 'BTI325 - Web Programming - Lab 5' → ('BTI325', 'Lab 5').

    Falls back to ('Unknown', summary) when no ' - ' separator is found.
    """
    parts = summary.split(" - ")
    if len(parts) < 2:
        return "Unknown", summary
    return parts[0].strip(), parts[-1].strip()


def _normalise_to_utc(dt: datetime | object) -> datetime:
    """Convert a date or datetime to a UTC-aware datetime."""
    from datetime import date

    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    # date with no time component — treat as midnight UTC
    if isinstance(dt, date):
        return datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)

    raise ICalParseError(f"Unexpected DTSTART type: {type(dt)}")
