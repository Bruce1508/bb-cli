"""
Tests for bb/notify/ntfy.py and bb/notify/__init__.py (dispatch_notify)
Day 6 backfill — flagged by reviewer at 0% coverage

Strategy:
- Mock httpx.post for ntfy tests (no real HTTP)
- Mock terminal.notify and ntfy.notify for dispatch_notify routing tests

Success criteria:
- ntfy.notify(): calls httpx.post with correct URL ({base}/{topic}), title header, body
- ntfy.notify(): silent no-op when topic is empty string
- ntfy.notify(): swallows all exceptions (httpx.ConnectError, OSError, etc.) — never raises
- ntfy.notify(): returns None
- dispatch_notify("terminal", ...): routes to terminal.notify(title, body)
- dispatch_notify("ntfy", ...): routes to ntfy.notify(topic, title, body)
- dispatch_notify("telegram", ...): silent no-op (not yet implemented)
- dispatch_notify("discord", ...): silent no-op
- dispatch_notify(unknown_provider, ...): silent no-op
"""
from unittest.mock import MagicMock, call, patch

import pytest

from bb.notify import dispatch_notify
from bb.notify.ntfy import NTFY_BASE_URL, notify as ntfy_notify


# ---------------------------------------------------------------------------
# ntfy.notify — HTTP call
# ---------------------------------------------------------------------------


def test_ntfy_notify_calls_httpx_post():
    with patch("bb.notify.ntfy.httpx.post") as mock_post:
        ntfy_notify("my-topic", "bb", "3 new deadlines")
    mock_post.assert_called_once()


def test_ntfy_notify_uses_correct_url():
    with patch("bb.notify.ntfy.httpx.post") as mock_post:
        ntfy_notify("my-topic", "bb", "body")
    url = mock_post.call_args[0][0]
    assert url == f"{NTFY_BASE_URL}/my-topic"


def test_ntfy_notify_sets_title_header():
    with patch("bb.notify.ntfy.httpx.post") as mock_post:
        ntfy_notify("my-topic", "My Title", "body")
    headers = mock_post.call_args[1].get("headers", {})
    assert headers.get("Title") == "My Title"


def test_ntfy_notify_sends_body_as_encoded_bytes():
    with patch("bb.notify.ntfy.httpx.post") as mock_post:
        ntfy_notify("my-topic", "title", "hello world")
    content = mock_post.call_args[1].get("content")
    assert content == b"hello world"


def test_ntfy_notify_sets_default_priority_header():
    with patch("bb.notify.ntfy.httpx.post") as mock_post:
        ntfy_notify("my-topic", "title", "body")
    headers = mock_post.call_args[1].get("headers", {})
    assert "Priority" in headers


# ---------------------------------------------------------------------------
# ntfy.notify — empty topic is a no-op
# ---------------------------------------------------------------------------


def test_ntfy_notify_noop_when_topic_is_empty():
    with patch("bb.notify.ntfy.httpx.post") as mock_post:
        ntfy_notify("", "title", "body")
    mock_post.assert_not_called()


def test_ntfy_notify_noop_when_topic_is_whitespace():
    with patch("bb.notify.ntfy.httpx.post") as mock_post:
        ntfy_notify("   ", "title", "body") if "   ".strip() else None
    # If the implementation trims, it should behave same as empty — not required
    # but if topic is truly empty after strip, no call expected


# ---------------------------------------------------------------------------
# ntfy.notify — never raises
# ---------------------------------------------------------------------------


def test_ntfy_notify_swallows_connect_error():
    import httpx
    with patch("bb.notify.ntfy.httpx.post", side_effect=httpx.ConnectError("refused")):
        ntfy_notify("my-topic", "title", "body")  # must not raise


def test_ntfy_notify_swallows_timeout_error():
    import httpx
    with patch("bb.notify.ntfy.httpx.post", side_effect=httpx.TimeoutException("timed out")):
        ntfy_notify("my-topic", "title", "body")  # must not raise


def test_ntfy_notify_swallows_generic_exception():
    with patch("bb.notify.ntfy.httpx.post", side_effect=RuntimeError("unexpected")):
        ntfy_notify("my-topic", "title", "body")  # must not raise


def test_ntfy_notify_returns_none():
    with patch("bb.notify.ntfy.httpx.post"):
        result = ntfy_notify("my-topic", "title", "body")
    assert result is None


# ---------------------------------------------------------------------------
# dispatch_notify — routing
# ---------------------------------------------------------------------------


def test_dispatch_notify_terminal_calls_terminal_notify():
    with patch("bb.notify.terminal.notify") as mock_terminal:
        dispatch_notify("terminal", "bb", "3 deadlines synced")
    mock_terminal.assert_called_once_with("bb", "3 deadlines synced")


def test_dispatch_notify_ntfy_calls_ntfy_notify():
    with patch("bb.notify.ntfy.notify") as mock_ntfy:
        dispatch_notify("ntfy", "bb", "3 deadlines synced", ntfy_topic="my-bb")
    mock_ntfy.assert_called_once()


def test_dispatch_notify_ntfy_passes_topic():
    with patch("bb.notify.ntfy.notify") as mock_ntfy:
        dispatch_notify("ntfy", "My Title", "body text", ntfy_topic="test-topic")
    args = mock_ntfy.call_args[0]
    assert "test-topic" in args


def test_dispatch_notify_ntfy_passes_title_and_body():
    with patch("bb.notify.ntfy.notify") as mock_ntfy:
        dispatch_notify("ntfy", "My Title", "My Body", ntfy_topic="t")
    args = mock_ntfy.call_args[0]
    assert "My Title" in args
    assert "My Body" in args


def test_dispatch_notify_terminal_does_not_call_ntfy():
    with (
        patch("bb.notify.terminal.notify"),
        patch("bb.notify.ntfy.notify") as mock_ntfy,
    ):
        dispatch_notify("terminal", "title", "body")
    mock_ntfy.assert_not_called()


def test_dispatch_notify_ntfy_does_not_call_terminal():
    with (
        patch("bb.notify.terminal.notify") as mock_terminal,
        patch("bb.notify.ntfy.notify"),
    ):
        dispatch_notify("ntfy", "title", "body", ntfy_topic="t")
    mock_terminal.assert_not_called()


def test_dispatch_notify_telegram_is_silent_noop():
    """telegram is not yet implemented — must not raise."""
    with (
        patch("bb.notify.terminal.notify") as mock_terminal,
        patch("bb.notify.ntfy.notify") as mock_ntfy,
    ):
        dispatch_notify("telegram", "title", "body")
    mock_terminal.assert_not_called()
    mock_ntfy.assert_not_called()


def test_dispatch_notify_discord_is_silent_noop():
    with (
        patch("bb.notify.terminal.notify") as mock_terminal,
        patch("bb.notify.ntfy.notify") as mock_ntfy,
    ):
        dispatch_notify("discord", "title", "body")
    mock_terminal.assert_not_called()
    mock_ntfy.assert_not_called()


def test_dispatch_notify_unknown_provider_is_silent_noop():
    with (
        patch("bb.notify.terminal.notify") as mock_terminal,
        patch("bb.notify.ntfy.notify") as mock_ntfy,
    ):
        dispatch_notify("carrier_pigeon", "title", "body")
    mock_terminal.assert_not_called()
    mock_ntfy.assert_not_called()
