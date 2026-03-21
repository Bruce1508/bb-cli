"""
Tests for bb/downloader.py — Downloader class

Strategy:
- Mock httpx.Client + SessionManager — no real HTTP, no real session file
- Test: cookie extraction, file write, conflict resolution, error handling
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from bb.downloader import DownloadError, Downloader
from bb.security.session import SessionError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sm(cookies: list[dict] | None = None) -> MagicMock:
    """Return a mock SessionManager whose decrypt_session returns given cookies."""
    sm = MagicMock()
    sm.decrypt_session.return_value = {
        "cookies": [{"name": "auth", "value": "tok123"}] if cookies is None else cookies,
        "origins": [],
    }
    return sm


def _make_mock_client(content: bytes = b"data", status: int = 200) -> MagicMock:
    """Return a mock httpx.Client whose stream() yields content."""
    mock_response = MagicMock()
    mock_response.headers = {"content-length": str(len(content))}
    mock_response.iter_bytes.return_value = [content]
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    if status >= 400:
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status}",
            request=MagicMock(),
            response=MagicMock(status_code=status),
        )
    else:
        mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.stream.return_value = mock_response
    mock_client.__enter__ = lambda s: s
    mock_client.__exit__ = MagicMock(return_value=False)
    return mock_client


# ---------------------------------------------------------------------------
# _extract_cookies
# ---------------------------------------------------------------------------


def test_extract_cookies_returns_name_value_dict():
    sm = _make_sm([{"name": "auth", "value": "tok"}, {"name": "session", "value": "abc"}])
    d = Downloader(sm)
    assert d._extract_cookies() == {"auth": "tok", "session": "abc"}


def test_extract_cookies_empty_when_no_cookies():
    sm = _make_sm([])
    d = Downloader(sm)
    assert d._extract_cookies() == {}


def test_extract_cookies_propagates_session_error():
    sm = MagicMock()
    sm.decrypt_session.side_effect = SessionError("no session")
    d = Downloader(sm)
    with pytest.raises(SessionError):
        d._extract_cookies()


# ---------------------------------------------------------------------------
# _resolve_filename
# ---------------------------------------------------------------------------


def test_resolve_filename_no_conflict(tmp_path):
    d = Downloader(MagicMock())
    result = d._resolve_filename(tmp_path, "file.pdf")
    assert result == tmp_path / "file.pdf"


def test_resolve_filename_first_conflict(tmp_path):
    (tmp_path / "file.pdf").touch()
    d = Downloader(MagicMock())
    result = d._resolve_filename(tmp_path, "file.pdf")
    assert result == tmp_path / "file_1.pdf"


def test_resolve_filename_multiple_conflicts(tmp_path):
    (tmp_path / "file.pdf").touch()
    (tmp_path / "file_1.pdf").touch()
    d = Downloader(MagicMock())
    result = d._resolve_filename(tmp_path, "file.pdf")
    assert result == tmp_path / "file_2.pdf"


def test_resolve_filename_no_extension(tmp_path):
    (tmp_path / "notes").touch()
    d = Downloader(MagicMock())
    result = d._resolve_filename(tmp_path, "notes")
    assert result == tmp_path / "notes_1"


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------


def test_download_creates_file(tmp_path):
    sm = _make_sm()
    d = Downloader(sm)
    mock_client = _make_mock_client(content=b"hello world")
    with patch("bb.downloader.httpx.Client", return_value=mock_client):
        result = d.download("https://example.com/file.pdf", tmp_path, "file.pdf")
    assert result == tmp_path / "file.pdf"
    assert (tmp_path / "file.pdf").read_bytes() == b"hello world"


def test_download_creates_dest_dir_if_missing(tmp_path):
    sm = _make_sm()
    d = Downloader(sm)
    dest = tmp_path / "new" / "subdir"
    mock_client = _make_mock_client(content=b"data")
    with patch("bb.downloader.httpx.Client", return_value=mock_client):
        d.download("https://example.com/file.pdf", dest, "file.pdf")
    assert dest.is_dir()


def test_download_raises_on_http_4xx(tmp_path):
    sm = _make_sm()
    d = Downloader(sm)
    mock_client = _make_mock_client(status=403)
    with patch("bb.downloader.httpx.Client", return_value=mock_client):
        with pytest.raises(DownloadError, match="HTTP 403"):
            d.download("https://example.com/file.pdf", tmp_path, "file.pdf")


def test_download_raises_on_timeout(tmp_path):
    sm = _make_sm()
    d = Downloader(sm)
    mock_client = MagicMock()
    mock_client.__enter__ = lambda s: s
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.stream.side_effect = httpx.TimeoutException("timeout")
    with patch("bb.downloader.httpx.Client", return_value=mock_client):
        with pytest.raises(DownloadError, match="Timeout"):
            d.download("https://example.com/file.pdf", tmp_path, "file.pdf")


def test_download_uses_get_method(tmp_path):
    """Ensure stream() is called with 'GET' as first argument."""
    sm = _make_sm()
    d = Downloader(sm)
    mock_client = _make_mock_client()
    with patch("bb.downloader.httpx.Client", return_value=mock_client):
        d.download("https://example.com/file.pdf", tmp_path, "file.pdf")
    mock_client.stream.assert_called_once()
    call_args = mock_client.stream.call_args
    assert call_args[0][0] == "GET"
