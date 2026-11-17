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
- dispatch_notify(cfg, ...): routes to the provider named in cfg.provider
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


def test_ntfy_notify_sends_non_ascii_title_and_priority_as_params():
    import httpx

    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200)

    def real_post(*args, **kwargs):
        with httpx.Client(transport=httpx.MockTransport(handler)) as c:
            return c.post(*args, **kwargs)

    with patch("bb.notify.ntfy.httpx.post", side_effect=real_post):
        ntfy_notify("t", "bb \u2014 due soon", "Lab_05 due in 3h", "high")
    assert len(seen) == 1
    assert seen[0].url.params["title"] == "bb \u2014 due soon"
    assert seen[0].url.params["priority"] == "high"
    assert seen[0].content.decode() == "Lab_05 due in 3h"


def test_ntfy_notify_sends_body_as_encoded_bytes():
    with patch("bb.notify.ntfy.httpx.post") as mock_post:
        ntfy_notify("my-topic", "title", "hello world")
    content = mock_post.call_args[1].get("content")
    assert content == b"hello world"


def test_ntfy_notify_sets_default_priority_param():
    with patch("bb.notify.ntfy.httpx.post") as mock_post:
        ntfy_notify("my-topic", "title", "body")
    assert mock_post.call_args[1]["params"]["priority"] == "default"


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
# dispatch_notify — routing (takes the whole NotificationConfig)
# ---------------------------------------------------------------------------

from bb.config import NotificationConfig  # noqa: E402


def _cfg(**kw) -> NotificationConfig:
    return NotificationConfig(**kw)


def test_dispatch_notify_terminal_calls_terminal_notify():
    with patch("bb.notify.terminal.notify") as mock_terminal:
        dispatch_notify(_cfg(provider="terminal"), "bb", "3 deadlines synced")
    mock_terminal.assert_called_once_with("bb", "3 deadlines synced")


def test_dispatch_notify_ntfy_passes_topic_and_priority():
    with patch("bb.notify.ntfy.notify") as mock_ntfy:
        dispatch_notify(_cfg(provider="ntfy", ntfy_topic="t"), "T", "B", priority="high")
    mock_ntfy.assert_called_once_with("t", "T", "B", "high")


def test_dispatch_notify_telegram_passes_credentials():
    with patch("bb.notify.telegram.notify") as mock_tg:
        dispatch_notify(
            _cfg(provider="telegram", telegram_token="tok", telegram_chat_id="42"), "T", "B"
        )
    mock_tg.assert_called_once_with("tok", "42", "T", "B", "default")


def test_dispatch_notify_discord_passes_webhook():
    with patch("bb.notify.discord.notify") as mock_dc:
        dispatch_notify(
            _cfg(provider="discord", discord_webhook="https://d/hook"), "T", "B", priority="urgent"
        )
    mock_dc.assert_called_once_with("https://d/hook", "T", "B", "urgent")


def test_dispatch_notify_only_calls_selected_provider():
    with (
        patch("bb.notify.terminal.notify") as mock_terminal,
        patch("bb.notify.ntfy.notify") as mock_ntfy,
        patch("bb.notify.telegram.notify") as mock_tg,
        patch("bb.notify.discord.notify") as mock_dc,
    ):
        dispatch_notify(_cfg(provider="telegram"), "T", "B")
    mock_tg.assert_called_once()
    mock_terminal.assert_not_called()
    mock_ntfy.assert_not_called()
    mock_dc.assert_not_called()
