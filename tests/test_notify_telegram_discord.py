from __future__ import annotations

from unittest.mock import patch

from bb.notify import discord as dc
from bb.notify import telegram as tg


# ---------------------------------------------------------------------------
# Telegram tests
# ---------------------------------------------------------------------------

def test_telegram_calls_correct_url_and_payload():
    with patch("bb.notify.telegram.httpx.post") as mock_post:
        tg.notify(
            token="BOT_TOKEN_123",
            chat_id="CHAT_456",
            title="Deadline soon",
            body="Assignment 1 is due in 2 hours",
        )
        mock_post.assert_called_once()
        url = mock_post.call_args.args[0]
        assert "BOT_TOKEN_123" in url
        assert "sendMessage" in url
        payload = mock_post.call_args.kwargs["json"]
        assert payload["chat_id"] == "CHAT_456"
        assert "Deadline soon" in payload["text"]
        assert "Assignment 1 is due in 2 hours" in payload["text"]
        assert payload["parse_mode"] == "Markdown"


def test_telegram_high_priority_prefixes_title():
    with patch("bb.notify.telegram.httpx.post") as mock_post:
        tg.notify(token="TOK", chat_id="CID", title="Grade posted", body="95/100", priority="high")
        payload = mock_post.call_args.kwargs["json"]
        assert payload["text"].startswith("**🔴 Grade posted**")


def test_telegram_default_priority_no_prefix():
    with patch("bb.notify.telegram.httpx.post") as mock_post:
        tg.notify(token="TOK", chat_id="CID", title="New announcement", body="Notes", priority="default")
        payload = mock_post.call_args.kwargs["json"]
        assert "🔴" not in payload["text"]
        assert "**New announcement**" in payload["text"]


def test_telegram_empty_token_no_http_call():
    with patch("bb.notify.telegram.httpx.post") as mock_post:
        tg.notify(token="", chat_id="CHAT_456", title="T", body="B")
        mock_post.assert_not_called()


def test_telegram_empty_chat_id_no_http_call():
    with patch("bb.notify.telegram.httpx.post") as mock_post:
        tg.notify(token="TOK", chat_id="", title="T", body="B")
        mock_post.assert_not_called()


def test_telegram_httpx_exception_is_silent():
    with patch("bb.notify.telegram.httpx.post", side_effect=Exception("network error")):
        tg.notify(token="TOK", chat_id="CID", title="T", body="B")  # must not raise


# ---------------------------------------------------------------------------
# Discord tests
# ---------------------------------------------------------------------------

def test_discord_calls_correct_webhook_url_and_payload():
    webhook = "https://discord.com/api/webhooks/123/abc"
    with patch("bb.notify.discord.httpx.post") as mock_post:
        dc.notify(webhook_url=webhook, title="Assignment graded", body="88/100 on Lab 3")
        mock_post.assert_called_once()
        url = mock_post.call_args.args[0]
        assert url == webhook
        payload = mock_post.call_args.kwargs["json"]
        assert "Assignment graded" in payload["content"]
        assert "88/100 on Lab 3" in payload["content"]


def test_discord_urgent_priority_prefixes_title():
    with patch("bb.notify.discord.httpx.post") as mock_post:
        dc.notify(
            webhook_url="https://discord.com/api/webhooks/1/x",
            title="Deadline",
            body="Due in 1 hour",
            priority="urgent",
        )
        payload = mock_post.call_args.kwargs["json"]
        assert "🔴 Deadline" in payload["content"]


def test_discord_empty_webhook_url_no_http_call():
    with patch("bb.notify.discord.httpx.post") as mock_post:
        dc.notify(webhook_url="", title="T", body="B")
        mock_post.assert_not_called()


def test_discord_httpx_exception_is_silent():
    with patch("bb.notify.discord.httpx.post", side_effect=ConnectionError("refused")):
        dc.notify(webhook_url="https://discord.com/api/webhooks/1/x", title="T", body="B")
