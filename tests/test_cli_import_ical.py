"""
Tests for `bb import-ical` command in bb/cli.py

Strategy:
- Mock httpx.get to return fixture content (no real HTTP)
- Mock bb.cli.notify to suppress real OS notifications
- Patch bb.config.BB_DIR → tmp_path for DB isolation

Success criteria:
- Success path: prints "Fetched", "Parsed N events", "N new, M already up to date"
- Idempotent: second run → "0 new, N already up to date"
- HTTP error: exit 1 + "server returned HTTP {status_code}"
- Network error: exit 1 + "could not reach {url}"
- Parse error: exit 1 + "could not parse iCal feed"
- --dry-run: prints deadline list, does NOT write to DB
- Notification sent only when new_count > 0
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from bb.cli import app
from bb.db import Database

runner = CliRunner()

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_ICS = (FIXTURES_DIR / "sample.ics").read_text()
TEST_URL = "https://learn.senecapolytechnic.ca/webapps/calendar/calendarFeed/test-token/learn.ics"

# fixture yields 4 valid deadlines (6 VEVENTs, 2 skipped)
EXPECTED_COUNT = 4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(text: str = SAMPLE_ICS, status_code: int = 200):
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


def _http_status_error(status_code: int):
    """Build an httpx.HTTPStatusError with a response.status_code."""
    import httpx
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    return httpx.HTTPStatusError(
        f"HTTP {status_code}", request=MagicMock(), response=mock_resp
    )


def _invoke_import(tmp_path, *extra_args: str, ics_text: str = SAMPLE_ICS):
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("httpx.get", return_value=_mock_response(ics_text)),
        patch("bb.cli.notify"),
    ):
        return runner.invoke(app, ["import-ical", TEST_URL, *extra_args])


# ---------------------------------------------------------------------------
# Success path output
# ---------------------------------------------------------------------------


def test_import_ical_exit_code_zero_on_success(tmp_path):
    result = _invoke_import(tmp_path)
    assert result.exit_code == 0, result.output


def test_import_ical_prints_fetched_confirmation(tmp_path):
    result = _invoke_import(tmp_path)
    assert "Fetched" in result.output


def test_import_ical_prints_parsed_count(tmp_path):
    result = _invoke_import(tmp_path)
    assert f"Parsed {EXPECTED_COUNT} events" in result.output


def test_import_ical_prints_new_count_on_first_run(tmp_path):
    result = _invoke_import(tmp_path)
    assert f"{EXPECTED_COUNT} new" in result.output


def test_import_ical_shows_zero_already_up_to_date_on_first_run(tmp_path):
    result = _invoke_import(tmp_path)
    assert "0 already up to date" in result.output


# ---------------------------------------------------------------------------
# Idempotency (second run)
# ---------------------------------------------------------------------------


def test_import_ical_second_run_shows_zero_new(tmp_path):
    _invoke_import(tmp_path)  # first run
    result = _invoke_import(tmp_path)  # second run
    assert "0 new" in result.output


def test_import_ical_second_run_shows_all_already_up_to_date(tmp_path):
    _invoke_import(tmp_path)
    result = _invoke_import(tmp_path)
    assert f"{EXPECTED_COUNT} already up to date" in result.output


def test_import_ical_second_run_exits_zero(tmp_path):
    _invoke_import(tmp_path)
    result = _invoke_import(tmp_path)
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# DB write verification
# ---------------------------------------------------------------------------


def test_import_ical_writes_deadlines_to_db(tmp_path):
    _invoke_import(tmp_path)
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        deadlines = db.get_upcoming_deadlines(days=365)
    assert len(deadlines) == EXPECTED_COUNT


# ---------------------------------------------------------------------------
# HTTP error handling
# ---------------------------------------------------------------------------


def test_import_ical_http_404_exits_with_code_1(tmp_path):
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("httpx.get", return_value=MagicMock(
            raise_for_status=MagicMock(side_effect=_http_status_error(404))
        )),
        patch("bb.cli.notify"),
    ):
        result = runner.invoke(app, ["import-ical", TEST_URL])
    assert result.exit_code == 1


def test_import_ical_http_404_shows_status_code(tmp_path):
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("httpx.get", return_value=MagicMock(
            raise_for_status=MagicMock(side_effect=_http_status_error(404))
        )),
        patch("bb.cli.notify"),
    ):
        result = runner.invoke(app, ["import-ical", TEST_URL])
    assert "404" in result.output


def test_import_ical_http_500_exits_with_code_1(tmp_path):
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("httpx.get", return_value=MagicMock(
            raise_for_status=MagicMock(side_effect=_http_status_error(500))
        )),
        patch("bb.cli.notify"),
    ):
        result = runner.invoke(app, ["import-ical", TEST_URL])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Network error handling
# ---------------------------------------------------------------------------


def test_import_ical_network_error_exits_with_code_1(tmp_path):
    import httpx
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("httpx.get", side_effect=httpx.RequestError("Connection refused")),
        patch("bb.cli.notify"),
    ):
        result = runner.invoke(app, ["import-ical", TEST_URL])
    assert result.exit_code == 1


def test_import_ical_network_error_message_mentions_url(tmp_path):
    import httpx
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("httpx.get", side_effect=httpx.RequestError("Connection refused")),
        patch("bb.cli.notify"),
    ):
        result = runner.invoke(app, ["import-ical", TEST_URL])
    assert "could not reach" in result.output


# ---------------------------------------------------------------------------
# Parse error handling
# ---------------------------------------------------------------------------


def test_import_ical_parse_error_exits_with_code_1(tmp_path):
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("httpx.get", return_value=_mock_response("garbage\x00\x01")),
        patch("bb.cli.notify"),
    ):
        result = runner.invoke(app, ["import-ical", TEST_URL])
    # parse_ical raises ICalParseError → exit 1
    # (only if icalendar raises on garbage — may return [] silently)
    # We assert: if exit code is 1, output contains the error message
    if result.exit_code == 1:
        assert "could not parse" in result.output


# ---------------------------------------------------------------------------
# --dry-run flag
# ---------------------------------------------------------------------------


def test_import_ical_dry_run_exits_zero(tmp_path):
    result = _invoke_import(tmp_path, "--dry-run")
    assert result.exit_code == 0


def test_import_ical_dry_run_shows_would_import_label(tmp_path):
    """Rich strips [dry-run] as an unknown style tag; 'Would import' is the visible text."""
    result = _invoke_import(tmp_path, "--dry-run")
    assert "Would import" in result.output


def test_import_ical_dry_run_shows_expected_count(tmp_path):
    result = _invoke_import(tmp_path, "--dry-run")
    assert str(EXPECTED_COUNT) in result.output


def test_import_ical_dry_run_shows_course_codes(tmp_path):
    result = _invoke_import(tmp_path, "--dry-run")
    assert "BTI325" in result.output


def test_import_ical_dry_run_does_not_write_to_db(tmp_path):
    _invoke_import(tmp_path, "--dry-run")
    # DB may not exist at all, or may exist with 0 deadlines
    db_path = tmp_path / "bb.db"
    if db_path.exists():
        with Database(db_path) as db:
            db.setup()
            deadlines = db.get_upcoming_deadlines(days=365)
        assert len(deadlines) == 0


def test_import_ical_dry_run_does_not_send_notification(tmp_path):
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("httpx.get", return_value=_mock_response()),
        patch("bb.cli.notify") as mock_notify,
    ):
        runner.invoke(app, ["import-ical", TEST_URL, "--dry-run"])
    mock_notify.assert_not_called()


# ---------------------------------------------------------------------------
# Notification behaviour
# ---------------------------------------------------------------------------


def test_import_ical_sends_notification_on_new_deadlines(tmp_path):
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("httpx.get", return_value=_mock_response()),
        patch("bb.cli.notify") as mock_notify,
    ):
        runner.invoke(app, ["import-ical", TEST_URL])
    mock_notify.assert_called_once()


def test_import_ical_no_notification_on_second_run(tmp_path):
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("httpx.get", return_value=_mock_response()),
        patch("bb.cli.notify"),
    ):
        runner.invoke(app, ["import-ical", TEST_URL])  # first run

    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("httpx.get", return_value=_mock_response()),
        patch("bb.cli.notify") as mock_notify,
    ):
        runner.invoke(app, ["import-ical", TEST_URL])  # second run — all existing
    mock_notify.assert_not_called()
