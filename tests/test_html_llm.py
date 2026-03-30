"""Tests for bb/parsers/html_llm.py — LLM-based HTML extractor."""
from __future__ import annotations

import importlib
import json
import sys
import types
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ollama_mock(return_content: str) -> types.ModuleType:
    """Return a fake ollama module whose chat() returns a message with given content."""
    mock_module = types.ModuleType("ollama")
    response = MagicMock()
    response.message.content = return_content
    mock_module.chat = MagicMock(return_value=response)
    return mock_module


def _fresh_html_llm():
    """Reload html_llm to force lazy imports to re-execute against current sys.modules."""
    import bb.parsers.html_llm as m
    importlib.reload(m)
    return m


# ---------------------------------------------------------------------------
# Test 1: get_model returns None → return [] without calling ollama.chat
# ---------------------------------------------------------------------------

def test_returns_empty_when_ollama_unavailable():
    mock_module = _make_ollama_mock("[]")
    sys.modules["ollama"] = mock_module

    with patch("bb.ai.providers.ollama.get_model", return_value=None):
        m = _fresh_html_llm()
        result = m.extract_from_html("<html>test</html>", "deadline items")

    assert result == []
    mock_module.chat.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2: ollama.chat raises → return [] without re-raising
# ---------------------------------------------------------------------------

def test_returns_empty_on_chat_exception():
    mock_module = types.ModuleType("ollama")
    mock_module.chat = MagicMock(side_effect=RuntimeError("connection refused"))
    sys.modules["ollama"] = mock_module

    with patch("bb.ai.providers.ollama.get_model", return_value="qwen2.5:7b"):
        m = _fresh_html_llm()
        result = m.extract_from_html("<html>test</html>", "announcements")

    assert result == []


# ---------------------------------------------------------------------------
# Test 3: valid JSON array → return parsed list
# ---------------------------------------------------------------------------

def test_returns_parsed_list_on_valid_json():
    payload = [{"title": "Assignment 1", "due": "2026-04-01"}]
    sys.modules["ollama"] = _make_ollama_mock(json.dumps(payload))

    with patch("bb.ai.providers.ollama.get_model", return_value="qwen2.5:7b"):
        m = _fresh_html_llm()
        result = m.extract_from_html("<html>some html</html>", "deadline items")

    assert result == payload


# ---------------------------------------------------------------------------
# Test 4: malformed JSON → return []
# ---------------------------------------------------------------------------

def test_returns_empty_on_malformed_json():
    sys.modules["ollama"] = _make_ollama_mock("this is not json {{{")

    with patch("bb.ai.providers.ollama.get_model", return_value="qwen2.5:7b"):
        m = _fresh_html_llm()
        result = m.extract_from_html("<html>test</html>", "grades")

    assert result == []


# ---------------------------------------------------------------------------
# Test 5: valid JSON but not a list → return []
# ---------------------------------------------------------------------------

def test_returns_empty_when_json_is_not_list():
    sys.modules["ollama"] = _make_ollama_mock(json.dumps({"key": "value"}))

    with patch("bb.ai.providers.ollama.get_model", return_value="qwen2.5:7b"):
        m = _fresh_html_llm()
        result = m.extract_from_html("<html>test</html>", "course list")

    assert result == []


# ---------------------------------------------------------------------------
# Test 6: explicit ollama_model bypasses get_model
# ---------------------------------------------------------------------------

def test_explicit_model_used_when_provided():
    payload = [{"course": "BTP200"}]
    mock_module = _make_ollama_mock(json.dumps(payload))
    sys.modules["ollama"] = mock_module

    with patch("bb.ai.providers.ollama.get_model", return_value="auto-model") as mock_get:
        m = _fresh_html_llm()
        result = m.extract_from_html(
            "<html>test</html>",
            "courses",
            ollama_model="llama3.2:3b",
        )

    mock_get.assert_not_called()
    call_kwargs = mock_module.chat.call_args
    used_model = (
        call_kwargs.kwargs.get("model")
        or (call_kwargs.args[0] if call_kwargs.args else None)
    )
    assert used_model == "llama3.2:3b"
    assert result == payload


# ---------------------------------------------------------------------------
# Test 7: ollama_model=None triggers get_model("") call
# ---------------------------------------------------------------------------

def test_get_model_called_when_no_explicit_model():
    payload = [{"item": "quiz"}]
    sys.modules["ollama"] = _make_ollama_mock(json.dumps(payload))

    with patch("bb.ai.providers.ollama.get_model", return_value="qwen3:8b") as mock_get:
        m = _fresh_html_llm()
        result = m.extract_from_html("<html>test</html>", "quiz items")

    mock_get.assert_called_once_with("")
    assert result == payload
