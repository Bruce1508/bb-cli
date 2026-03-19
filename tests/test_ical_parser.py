"""
Tests for bb/parsers/ical.py

All tests use the fixture file or inline .ics strings — no HTTP, no DB.

Success criteria:
- parse_ical returns a list of Deadline objects
- Events missing DTSTART or with empty SUMMARY are skipped
- course = first segment of ' - '-separated SUMMARY; title = last segment
- No separator → course='Unknown', title=full SUMMARY
- All due_at values are UTC-aware datetimes
- date-only DTSTART → midnight UTC datetime
- id is a 64-char hex string (full SHA-256)
- source == 'ical' on every result
- Two identical VEVENTs produce the same id (deterministic hash)
- Malformed .ics raises ICalParseError
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from bb.parsers.ical import ICalParseError, parse_ical

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_ICS = (FIXTURES_DIR / "sample.ics").read_text()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ics(*summaries_and_dtstart: tuple[str, str]) -> str:
    """Build a minimal valid .ics from (summary, dtstart_line) pairs."""
    events = []
    for summary, dtstart in summaries_and_dtstart:
        events.append(
            f"BEGIN:VEVENT\n{dtstart}\nSUMMARY:{summary}\nEND:VEVENT"
        )
    body = "\n".join(events)
    return f"BEGIN:VCALENDAR\nVERSION:2.0\n{body}\nEND:VCALENDAR"


# ---------------------------------------------------------------------------
# Basic contract
# ---------------------------------------------------------------------------


def test_parse_returns_list():
    result = parse_ical(SAMPLE_ICS)
    assert isinstance(result, list)


def test_parse_correct_count():
    """Fixture has 6 VEVENTs: 2 skipped (no DTSTART, empty SUMMARY) → 4 valid."""
    result = parse_ical(SAMPLE_ICS)
    assert len(result) == 4


def test_source_is_ical_on_all_results():
    result = parse_ical(SAMPLE_ICS)
    assert all(d.source == "ical" for d in result)


# ---------------------------------------------------------------------------
# SUMMARY extraction
# ---------------------------------------------------------------------------


def test_course_code_extracted():
    """'BTI325 - Web Programming - Lab 5' → course='BTI325'."""
    result = parse_ical(SAMPLE_ICS)
    bti325 = next(d for d in result if d.course == "BTI325")
    assert bti325.course == "BTI325"


def test_title_is_last_segment():
    """'BTI325 - Web Programming - Lab 5' → title='Lab 5'."""
    result = parse_ical(SAMPLE_ICS)
    bti325 = next(d for d in result if d.course == "BTI325")
    assert bti325.title == "Lab 5"


def test_no_separator_summary_course_is_unknown():
    """'Final Exam Period' (no ' - ') → course='Unknown'."""
    result = parse_ical(SAMPLE_ICS)
    unknown = next(d for d in result if d.course == "Unknown")
    assert unknown.course == "Unknown"


def test_no_separator_summary_title_is_full_string():
    """'Final Exam Period' (no ' - ') → title='Final Exam Period'."""
    result = parse_ical(SAMPLE_ICS)
    unknown = next(d for d in result if d.course == "Unknown")
    assert unknown.title == "Final Exam Period"


def test_two_segment_summary_parsed_correctly():
    """'OOP244 - Workshop 7' → course='OOP244', title='Workshop 7'."""
    ics = _make_ics(("OOP244 - Workshop 7", "DTSTART:20260328T235900Z"))
    result = parse_ical(ics)
    assert len(result) == 1
    assert result[0].course == "OOP244"
    assert result[0].title == "Workshop 7"


def test_three_segment_summary_middle_discarded():
    """'BTP200 - Internet Technologies - Assignment 2' → title='Assignment 2' (middle ignored)."""
    result = parse_ical(SAMPLE_ICS)
    btp = next(d for d in result if d.course == "BTP200")
    assert btp.title == "Assignment 2"


# ---------------------------------------------------------------------------
# DTSTART normalisation
# ---------------------------------------------------------------------------


def test_due_at_is_utc_aware_on_all_results():
    """All due_at values must be UTC-aware (utcoffset == 0)."""
    result = parse_ical(SAMPLE_ICS)
    for d in result:
        assert d.due_at.utcoffset() == timedelta(0), (
            f"{d.course} {d.title}: due_at is not UTC ({d.due_at})"
        )


def test_date_only_dtstart_converted_to_midnight_utc():
    """DTSTART;VALUE=DATE:20260328 → datetime(2026, 3, 28, 0, 0, tzinfo=utc)."""
    result = parse_ical(SAMPLE_ICS)
    oop = next(d for d in result if d.course == "OOP244")
    assert oop.due_at == datetime(2026, 3, 28, 0, 0, 0, tzinfo=timezone.utc)


def test_naive_datetime_treated_as_utc():
    """Naive DTSTART (no Z, no TZID) → treated as UTC."""
    ics = _make_ics(("BTI325 - Web - Lab 1", "DTSTART:20260325T235900"))
    result = parse_ical(ics)
    assert len(result) == 1
    assert result[0].due_at == datetime(2026, 3, 25, 23, 59, 0, tzinfo=timezone.utc)


def test_utc_z_datetime_preserved():
    """DTSTART:20260325T235900Z → datetime(2026, 3, 25, 23, 59, tzinfo=utc)."""
    ics = _make_ics(("BTI325 - Web - Lab 1", "DTSTART:20260325T235900Z"))
    result = parse_ical(ics)
    assert result[0].due_at == datetime(2026, 3, 25, 23, 59, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Skipped events
# ---------------------------------------------------------------------------


def test_missing_dtstart_skipped():
    """Event with no DTSTART must not appear in output."""
    result = parse_ical(SAMPLE_ICS)
    titles = [d.title for d in result]
    assert "Missing DTSTART" not in titles


def test_empty_summary_skipped():
    """Event with empty SUMMARY must not appear in output."""
    result = parse_ical(SAMPLE_ICS)
    assert all(d.title.strip() != "" for d in result)


def test_empty_summary_inline():
    """Inline test: SUMMARY: (empty) → event skipped."""
    ics = (
        "BEGIN:VCALENDAR\nVERSION:2.0\n"
        "BEGIN:VEVENT\nDTSTART:20260325T235900Z\nSUMMARY:\nEND:VEVENT\n"
        "END:VCALENDAR"
    )
    result = parse_ical(ics)
    assert result == []


def test_missing_dtstart_inline():
    """Inline test: no DTSTART line → event skipped."""
    ics = (
        "BEGIN:VCALENDAR\nVERSION:2.0\n"
        "BEGIN:VEVENT\nSUMMARY:BTI325 - Web - Lab 1\nEND:VEVENT\n"
        "END:VCALENDAR"
    )
    result = parse_ical(ics)
    assert result == []


# ---------------------------------------------------------------------------
# ID / dedup
# ---------------------------------------------------------------------------


def test_id_is_64_char_hex_string():
    """id must be a full SHA-256 hexdigest (64 chars, valid hex)."""
    result = parse_ical(SAMPLE_ICS)
    for d in result:
        assert len(d.id) == 64, f"id length {len(d.id)} != 64 for {d.course}/{d.title}"
        int(d.id, 16)  # raises ValueError if not valid hex


def test_duplicate_vevent_produces_same_id():
    """Two identical VEVENTs must produce the same deterministic id."""
    ics = (
        "BEGIN:VCALENDAR\nVERSION:2.0\n"
        "BEGIN:VEVENT\nDTSTART:20260325T235900Z\nSUMMARY:BTI325 - Web - Lab 1\nEND:VEVENT\n"
        "BEGIN:VEVENT\nDTSTART:20260325T235900Z\nSUMMARY:BTI325 - Web - Lab 1\nEND:VEVENT\n"
        "END:VCALENDAR"
    )
    result = parse_ical(ics)
    assert len(result) == 2
    assert result[0].id == result[1].id


def test_different_events_have_different_ids():
    """Different SUMMARY/DTSTART combinations must produce different ids."""
    result = parse_ical(SAMPLE_ICS)
    ids = [d.id for d in result]
    assert len(ids) == len(set(ids)), "Duplicate ids found for distinct events"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_malformed_ical_raises_ical_parse_error():
    """Truly malformed .ics input must raise ICalParseError."""
    with pytest.raises(ICalParseError):
        parse_ical("garbage\x00\x01\x02")


def test_ical_parse_error_is_subclass_of_value_error():
    assert issubclass(ICalParseError, ValueError)


def test_empty_calendar_returns_empty_list():
    """A valid but empty VCALENDAR (no VEVENTs) returns []."""
    ics = "BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR"
    result = parse_ical(ics)
    assert result == []
