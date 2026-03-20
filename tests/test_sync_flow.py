"""
Tests for bb/sync.py — sync engine (Day 5/6 backfill, flagged by reviewer at 0% coverage)

Strategy:
- Use real in-memory-style SQLite DB (tmp_path) for upsert verification
- Mock httpx.get for sync_ical; mock time.sleep to skip backoff delays
- Mock adapter.fetch_activity_stream / fetch_grades for sync_stream / sync_grades
- Direct unit tests of pure routing logic — no Playwright

Success criteria:
- sync_ical: returns (new, updated) counts correctly
- sync_ical: retries up to 3 times on RequestError with sleep between attempts
- sync_ical: re-raises last exception after all 3 retries exhausted
- sync_ical: succeeds on 3rd attempt after 2 failures
- sync_ical: raises immediately on HTTPStatusError (after retries)
- sync_stream: routes Deadline/Announcement/GradeItem to correct upsert
- sync_stream: returns (d_new, a_new, g_new) tuple
- sync_stream: calls _save_snapshot when 0 items scraped
- sync_stream: does NOT call _save_snapshot when items returned
- sync_grades: counts only new grade items
- sync_grades: returns 0 when adapter returns empty list
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from bb.adapters.base import Announcement, Deadline, GradeItem
from bb.db import Database
from bb.sync import sync_grades, sync_ical, sync_stream

TEST_URL = "https://learn.example.com/ical/feed.ics"

MINIMAL_ICS = (
    "BEGIN:VCALENDAR\nVERSION:2.0\n"
    "BEGIN:VEVENT\nDTSTART:20260325T235900Z\n"
    "SUMMARY:BTI325 - Web - Lab 1\nEND:VEVENT\n"
    "END:VCALENDAR"
)

EMPTY_ICS = "BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_http_response(text: str = MINIMAL_ICS) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.raise_for_status.return_value = None
    return resp


def _make_deadline(id: str = "dl-1", days: float = 3.0) -> Deadline:
    return Deadline(
        id=id,
        course="BTI325",
        title="Lab 1",
        due_at=datetime.now(timezone.utc) + timedelta(days=days),
        source="stream",
    )


def _make_announcement(id: str = "ann-1") -> Announcement:
    return Announcement(
        id=id,
        course="BTI325",
        title="Lab 1 Updated",
        body="New requirements posted.",
        posted_at=datetime.now(timezone.utc),
        read_at=None,
    )


def _make_grade(id: str = "g-1") -> GradeItem:
    return GradeItem(
        id=id, course="BTI325", item="Lab 1", score=18.0, out_of=20.0, status="graded"
    )


# ---------------------------------------------------------------------------
# sync_ical — basic counts
# ---------------------------------------------------------------------------


def test_sync_ical_returns_new_count_on_first_run(tmp_path):
    with (
        patch("bb.sync.httpx.get", return_value=_mock_http_response()),
        patch("bb.sync.time.sleep"),
        Database(tmp_path / "bb.db") as db,
    ):
        db.setup()
        new, updated = sync_ical(TEST_URL, db)
    assert new == 1
    assert updated == 0


def test_sync_ical_returns_updated_count_on_second_run(tmp_path):
    with (
        patch("bb.sync.httpx.get", return_value=_mock_http_response()),
        patch("bb.sync.time.sleep"),
        Database(tmp_path / "bb.db") as db,
    ):
        db.setup()
        sync_ical(TEST_URL, db)  # first run
        new, updated = sync_ical(TEST_URL, db)  # second run — same data
    assert new == 0
    assert updated == 1


def test_sync_ical_empty_feed_returns_zero_zero(tmp_path):
    with (
        patch("bb.sync.httpx.get", return_value=_mock_http_response(EMPTY_ICS)),
        patch("bb.sync.time.sleep"),
        Database(tmp_path / "bb.db") as db,
    ):
        db.setup()
        new, updated = sync_ical(TEST_URL, db)
    assert new == 0
    assert updated == 0


# ---------------------------------------------------------------------------
# sync_ical — retry logic
# ---------------------------------------------------------------------------


def test_sync_ical_retries_on_request_error(tmp_path):
    """sync_ical retries up to 3 times and succeeds on the 3rd attempt."""
    call_count = 0

    def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.RequestError("Connection refused")
        return _mock_http_response(EMPTY_ICS)

    with (
        patch("bb.sync.httpx.get", side_effect=mock_get),
        patch("bb.sync.time.sleep"),
        Database(tmp_path / "bb.db") as db,
    ):
        db.setup()
        sync_ical(TEST_URL, db)

    assert call_count == 3


def test_sync_ical_sleeps_between_retries(tmp_path):
    """Exponential backoff: sleep is called between retry attempts."""
    def mock_get(*args, **kwargs):
        raise httpx.RequestError("Connection refused")

    with (
        patch("bb.sync.httpx.get", side_effect=mock_get),
        patch("bb.sync.time.sleep") as mock_sleep,
    ):
        with pytest.raises(httpx.RequestError):
            with Database(tmp_path / "bb.db") as db:
                db.setup()
                sync_ical(TEST_URL, db)

    assert mock_sleep.call_count >= 2  # slept between each of the 3 attempts


def test_sync_ical_reraises_after_all_retries_exhausted(tmp_path):
    """After 3 failures, the last exception propagates to the caller."""
    with (
        patch("bb.sync.httpx.get", side_effect=httpx.RequestError("timeout")),
        patch("bb.sync.time.sleep"),
    ):
        with pytest.raises(httpx.RequestError):
            with Database(tmp_path / "bb.db") as db:
                db.setup()
                sync_ical(TEST_URL, db)


def test_sync_ical_reraises_http_status_error(tmp_path):
    """Non-2xx response is re-raised (after retries)."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404", request=MagicMock(), response=MagicMock(status_code=404)
    )
    with (
        patch("bb.sync.httpx.get", return_value=mock_resp),
        patch("bb.sync.time.sleep"),
    ):
        with pytest.raises(httpx.HTTPStatusError):
            with Database(tmp_path / "bb.db") as db:
                db.setup()
                sync_ical(TEST_URL, db)


# ---------------------------------------------------------------------------
# sync_stream — routing
# ---------------------------------------------------------------------------


def test_sync_stream_returns_tuple_of_three(tmp_path):
    adapter = MagicMock()
    adapter.fetch_activity_stream.return_value = []
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        result = sync_stream(adapter, db)
    assert len(result) == 3


def test_sync_stream_counts_new_deadlines(tmp_path):
    adapter = MagicMock()
    adapter.fetch_activity_stream.return_value = [_make_deadline("dl-1")]
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        d_new, a_new, g_new = sync_stream(adapter, db)
    assert d_new == 1
    assert a_new == 0
    assert g_new == 0


def test_sync_stream_counts_new_announcements(tmp_path):
    adapter = MagicMock()
    adapter.fetch_activity_stream.return_value = [_make_announcement()]
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        d_new, a_new, g_new = sync_stream(adapter, db)
    assert d_new == 0
    assert a_new == 1
    assert g_new == 0


def test_sync_stream_counts_new_grades(tmp_path):
    adapter = MagicMock()
    adapter.fetch_activity_stream.return_value = [_make_grade()]
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        d_new, a_new, g_new = sync_stream(adapter, db)
    assert d_new == 0
    assert a_new == 0
    assert g_new == 1


def test_sync_stream_routes_mixed_items_correctly(tmp_path):
    adapter = MagicMock()
    adapter.fetch_activity_stream.return_value = [
        _make_deadline("dl-1"),
        _make_announcement("ann-1"),
        _make_grade("g-1"),
    ]
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        d_new, a_new, g_new = sync_stream(adapter, db)
    assert d_new == 1
    assert a_new == 1
    assert g_new == 1


def test_sync_stream_second_run_returns_zeros(tmp_path):
    """Items already in DB are not counted as new."""
    adapter = MagicMock()
    items = [_make_deadline("dl-1"), _make_announcement("ann-1")]
    adapter.fetch_activity_stream.return_value = items
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        sync_stream(adapter, db)  # first run
        d_new, a_new, g_new = sync_stream(adapter, db)  # second run
    assert d_new == 0
    assert a_new == 0


def test_sync_stream_calls_save_snapshot_when_zero_items(tmp_path):
    adapter = MagicMock()
    adapter.fetch_activity_stream.return_value = []
    with patch("bb.sync._save_snapshot") as mock_snapshot:
        with Database(tmp_path / "bb.db") as db:
            db.setup()
            sync_stream(adapter, db)
    mock_snapshot.assert_called_once_with(adapter)


def test_sync_stream_does_not_call_save_snapshot_when_items_present(tmp_path):
    adapter = MagicMock()
    adapter.fetch_activity_stream.return_value = [_make_deadline()]
    with patch("bb.sync._save_snapshot") as mock_snapshot:
        with Database(tmp_path / "bb.db") as db:
            db.setup()
            sync_stream(adapter, db)
    mock_snapshot.assert_not_called()


# ---------------------------------------------------------------------------
# sync_grades
# ---------------------------------------------------------------------------


def test_sync_grades_returns_int(tmp_path):
    adapter = MagicMock()
    adapter.fetch_grades.return_value = []
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        result = sync_grades(adapter, db)
    assert isinstance(result, int)


def test_sync_grades_returns_zero_when_no_items(tmp_path):
    adapter = MagicMock()
    adapter.fetch_grades.return_value = []
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        result = sync_grades(adapter, db)
    assert result == 0


def test_sync_grades_counts_new_items(tmp_path):
    adapter = MagicMock()
    adapter.fetch_grades.return_value = [_make_grade("g-1"), _make_grade("g-2")]
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        result = sync_grades(adapter, db)
    assert result == 2


def test_sync_grades_second_run_returns_zero(tmp_path):
    adapter = MagicMock()
    adapter.fetch_grades.return_value = [_make_grade("g-1")]
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        sync_grades(adapter, db)
        result = sync_grades(adapter, db)
    assert result == 0
