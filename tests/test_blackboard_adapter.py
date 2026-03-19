"""
Tests for bb/adapters/blackboard_ultra.py (Day 4 — auth methods + selectors)

Strategy:
- Mock SessionManager to avoid real session files / keyring
- Test _load_selectors directly with tmp_path and the real selectors file
- No real Playwright invoked

Success criteria:
- BlackboardUltraAdapter is registered as "blackboard_ultra" in the adapter registry
- check_session() returns the value from SessionManager.check_session_age()
- _load_selectors() returns {} when file is missing
- _load_selectors() parses a valid TOML file into a dict
- selectors/blackboard_ultra.toml exists and contains the required sections
- Day 5 stubs (fetch_activity_stream, fetch_grades, fetch_course_content) return correct types
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bb.adapters.blackboard_ultra import BlackboardUltraAdapter, _load_selectors
from bb.adapters.registry import get_adapter
from bb.security.session import SessionManager

SELECTORS_PATH = Path(__file__).parent.parent / "selectors" / "blackboard_ultra.toml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapter(session_status: str = "fresh") -> BlackboardUltraAdapter:
    """Create an adapter with a mocked SessionManager."""
    sm = MagicMock(spec=SessionManager)
    sm.check_session_age.return_value = session_status
    return BlackboardUltraAdapter(lms_url="https://learn.example.com", session_manager=sm)


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------


def test_blackboard_ultra_adapter_is_registered():
    cls = get_adapter("blackboard_ultra")
    assert cls is BlackboardUltraAdapter


# ---------------------------------------------------------------------------
# check_session delegation
# ---------------------------------------------------------------------------


def test_check_session_returns_fresh():
    adapter = _make_adapter("fresh")
    assert adapter.check_session() == "fresh"


def test_check_session_returns_uncertain():
    adapter = _make_adapter("uncertain")
    assert adapter.check_session() == "uncertain"


def test_check_session_returns_expired():
    adapter = _make_adapter("expired")
    assert adapter.check_session() == "expired"


def test_check_session_calls_session_manager_once():
    sm = MagicMock(spec=SessionManager)
    sm.check_session_age.return_value = "fresh"
    adapter = BlackboardUltraAdapter(lms_url="https://example.com", session_manager=sm)
    adapter.check_session()
    sm.check_session_age.assert_called_once()


# ---------------------------------------------------------------------------
# _load_selectors
# ---------------------------------------------------------------------------


def test_load_selectors_returns_empty_dict_when_file_missing(tmp_path):
    result = _load_selectors(tmp_path / "nonexistent.toml")
    assert result == {}


def test_load_selectors_returns_dict_when_file_exists(tmp_path):
    toml_file = tmp_path / "selectors.toml"
    toml_file.write_text("[auth]\ndashboard = 'header'\n")
    result = _load_selectors(toml_file)
    assert isinstance(result, dict)


def test_load_selectors_parses_section_keys(tmp_path):
    toml_file = tmp_path / "selectors.toml"
    toml_file.write_text("[auth]\ndashboard = 'header'\n[stream]\nitem = '.item'\n")
    result = _load_selectors(toml_file)
    assert "auth" in result
    assert "stream" in result


def test_load_selectors_parses_values_correctly(tmp_path):
    toml_file = tmp_path / "selectors.toml"
    toml_file.write_text("[auth]\ndashboard = 'header-element'\n")
    result = _load_selectors(toml_file)
    assert result["auth"]["dashboard"] == "header-element"


# ---------------------------------------------------------------------------
# selectors/blackboard_ultra.toml — structure verification
# ---------------------------------------------------------------------------


def test_selectors_file_exists():
    assert SELECTORS_PATH.exists(), f"Missing selectors file: {SELECTORS_PATH}"


def test_selectors_has_auth_section():
    result = _load_selectors(SELECTORS_PATH)
    assert "auth" in result, "selectors TOML missing [auth] section"


def test_selectors_has_activity_stream_section():
    result = _load_selectors(SELECTORS_PATH)
    assert "activity_stream" in result, "selectors TOML missing [activity_stream] section"


def test_selectors_auth_has_dashboard_indicator():
    result = _load_selectors(SELECTORS_PATH)
    assert "dashboard_indicator" in result["auth"]


def test_selectors_activity_stream_has_container():
    result = _load_selectors(SELECTORS_PATH)
    assert "container" in result["activity_stream"]


def test_selectors_activity_stream_has_item():
    result = _load_selectors(SELECTORS_PATH)
    assert "item" in result["activity_stream"]


# ---------------------------------------------------------------------------
# Day 5 stub methods — return correct types now
# ---------------------------------------------------------------------------


def test_fetch_activity_stream_stub_returns_list():
    adapter = _make_adapter()
    result = adapter.fetch_activity_stream()
    assert isinstance(result, list)


def test_fetch_activity_stream_stub_returns_empty_list():
    adapter = _make_adapter()
    assert adapter.fetch_activity_stream() == []


def test_fetch_grades_stub_returns_list():
    adapter = _make_adapter()
    result = adapter.fetch_grades()
    assert isinstance(result, list)


def test_fetch_grades_stub_returns_empty_list():
    adapter = _make_adapter()
    assert adapter.fetch_grades() == []


def test_fetch_course_content_stub_returns_object():
    adapter = _make_adapter()
    result = adapter.fetch_course_content("BTI325")
    assert result is not None
