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
    mock_client.stream.assert_called_once_with("GET", "https://example.com/file.pdf")


def test_download_cleans_up_partial_file_after_mid_download_timeout(tmp_path):
    """Partial file must be deleted when TimeoutException raised during iter_bytes."""
    sm = _make_sm()
    d = Downloader(sm)

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_bytes.side_effect = httpx.TimeoutException("read timeout")
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream.return_value = mock_response
    mock_client.__enter__ = lambda s: s
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("bb.downloader.httpx.Client", return_value=mock_client):
        with pytest.raises(DownloadError):
            d.download("https://example.com/file.pdf", tmp_path, "file.pdf")

    assert not (tmp_path / "file.pdf").exists()


from bb.db import Database  # noqa: E402
from bb.downloader import (  # noqa: E402
    collect_downloadable,
    download_items,
    ext_from_url,
)
from bb.models.content import ContentItem, find_items  # noqa: E402


class _FakeDL:
    def __init__(self, fail=()):
        self.fail = set(fail)

    def download(self, url, dest_dir, filename):
        if filename in self.fail:
            raise DownloadError("HTTP 403")
        dest_dir.mkdir(parents=True, exist_ok=True)
        p = dest_dir / filename
        p.write_bytes(b"x" * 2048)
        return p


def _items():
    week5 = ContentItem("folder", "Week 5", children=[
        ContentItem("file", "Slides", download_url="https://h/x/slides.pptx"),
    ])
    return [
        ContentItem("file", "Week 1", download_url="https://h/a/w1.pdf?x=1"),
        ContentItem("file", "Week 2", download_url="https://h/a/w2.pdf"),
        week5,
    ]


def test_ext_from_url():
    assert ext_from_url("https://h/a/w1.pdf?x=1") == ".pdf"
    assert ext_from_url(None) == ""


def test_collect_and_find():
    assert len(collect_downloadable(_items())) == 3
    assert [i.title for i in find_items(_items(), "week 5")] == ["Week 5"]


def test_download_items_reports_each_outcome(tmp_path):
    dest = tmp_path / "files" / "BTP200"
    dest.mkdir(parents=True)
    (dest / "Week 1.pdf").write_bytes(b"old")
    db = Database(tmp_path / "bb.db")
    db.setup()
    events = []
    report = download_items(
        _items()[:2], "BTP200", dest, _FakeDL(), db,
        on_event=lambda *e: events.append(e),
    )
    assert report.skipped == ["Week 1.pdf"]
    assert [p.name for p in report.saved] == ["Week 2.pdf"]
    assert db.get_downloads("BTP200")[0]["filename"] == "Week 2.pdf"
    assert [e[0] for e in events] == ["skipped", "saved"]


def test_download_items_failure_is_reported_not_raised(tmp_path):
    db = Database(tmp_path / "bb.db")
    db.setup()
    report = download_items(_items()[1:2], "BTP200", tmp_path / "d",
                            _FakeDL(fail={"Week 2.pdf"}), db)
    assert report.failed == [("Week 2.pdf", "HTTP 403")]
    assert report.saved == []


def test_safe_filename_never_escapes_or_hides():
    from bb.downloader import safe_filename
    def name(title, url="https://h/f.pdf"):
        return safe_filename(ContentItem("file", title, download_url=url))
    assert name("Week 1/Slides") == "Week 1_Slides.pdf"
    assert name("..\\..\\etc") == "_.._etc.pdf"
    assert name("..", url="https://h/noext") == "file"
    assert name("   ") == "file.pdf"
    assert name(".hidden") == "hidden.pdf"
    for t in ("../x", "..", "a\\b", "/abs"):
        assert "/" not in name(t) and "\\" not in name(t) and not name(t).startswith(".")
