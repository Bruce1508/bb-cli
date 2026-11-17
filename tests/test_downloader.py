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

from bb.downloader import DownloadError, Downloader, ambiguous_filenames
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
    assert dict(d._extract_cookies()) == {"auth": "tok", "session": "abc"}


def test_extract_cookies_empty_when_no_cookies():
    sm = _make_sm([])
    d = Downloader(sm)
    assert dict(d._extract_cookies()) == {}


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
    db.record_download("BTP200", "Week 1.pdf", str(dest / "Week 1.pdf"), 3,
                       url="https://h/a/w1.pdf?x=1")
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


def test_safe_filename_strips_control_chars_and_caps_length():
    from bb.downloader import safe_filename
    assert safe_filename(ContentItem("file", "a\x00b\x1fc\x7f", download_url="https://h/f.pdf")) \
        == "abc.pdf"
    long = safe_filename(ContentItem("file", "x" * 300, download_url="https://h/f.pdf"))
    assert long == "x" * 150 + ".pdf"


def test_download_items_survives_nul_and_overlong_titles(tmp_path):
    """Junk titles must never raise out of download_items and abort the rest of the batch."""
    db = Database(tmp_path / "bb.db")
    db.setup()
    items = [
        ContentItem("file", "bad\x00name", download_url="https://h/1.pdf"),
        ContentItem("file", "y" * 300, download_url="https://h/2.pdf"),
        ContentItem("file", "Normal", download_url="https://h/3.pdf"),
    ]
    report = download_items(items, "BTP200", tmp_path / "d", _FakeDL(), db)
    assert report.failed == []
    assert [p.name for p in report.saved] == ["badname.pdf", "y" * 150 + ".pdf", "Normal.pdf"]


def test_download_items_os_error_is_reported_per_item(tmp_path):
    class _Full(_FakeDL):
        def download(self, url, dest_dir, filename):
            if url.endswith("1.pdf"):
                raise OSError(28, "No space left on device")
            return super().download(url, dest_dir, filename)
    db = Database(tmp_path / "bb.db")
    db.setup()
    items = [ContentItem("file", "A", download_url="https://h/1.pdf"),
             ContentItem("file", "B", download_url="https://h/2.pdf")]
    report = download_items(items, "BTP200", tmp_path / "d", _Full(), db)
    assert [n for n, _ in report.failed] == ["A.pdf"]
    assert [p.name for p in report.saved] == ["B.pdf"]


def test_download_unlinks_partial_file_on_os_error(tmp_path):
    mock_client = _make_mock_client()
    mock_client.stream.return_value.iter_bytes.side_effect = OSError(28, "No space left")
    with patch("bb.downloader.httpx.Client", return_value=mock_client):
        with pytest.raises(OSError):
            Downloader(_make_sm()).download("https://h/f.pdf", tmp_path, "f.pdf")
    assert not (tmp_path / "f.pdf").exists()


def test_duplicate_titles_get_distinct_files_and_skip_on_rerun(tmp_path):
    """'Lecture Slides' in every week folder must not collapse into one file."""
    db = Database(tmp_path / "bb.db")
    db.setup()
    dest = tmp_path / "d"
    items = [ContentItem("file", "Lecture Slides", download_url="https://h/w1/s.pdf"),
             ContentItem("file", "Lecture Slides", download_url="https://h/w2/s.pdf")]
    first = download_items(items, "BTP200", dest, _FakeDL(), db)
    names = [p.name for p in first.saved]
    assert len(names) == 2 and len(set(names)) == 2
    second = download_items(items, "BTP200", dest, _FakeDL(), db)
    assert second.saved == [] and sorted(second.skipped) == sorted(names)


def test_same_title_in_a_later_call_does_not_reuse_the_other_weeks_file(tmp_path):
    db = Database(tmp_path / "bb.db")
    db.setup()
    dest = tmp_path / "d"
    w1 = ContentItem("file", "Lecture Slides", download_url="https://h/w1/s.pdf")
    w5 = ContentItem("file", "Lecture Slides", download_url="https://h/w5/s.pdf")
    download_items([w1], "BTP200", dest, _FakeDL(), db)
    report = download_items([w5], "BTP200", dest, _FakeDL(), db)
    assert report.skipped == []
    assert len(report.saved) == 1 and report.saved[0].name != "Lecture Slides.pdf"


def test_safe_filename_unique_hashes_before_the_extension():
    from bb.downloader import safe_filename
    item = ContentItem("file", "Week 1. Intro", download_url="https://h/w1/s.pdf")
    name = safe_filename(item, unique=True)
    assert name.startswith("Week 1. Intro-") and name.endswith(".pdf") and len(name) == 24


def test_session_cookies_are_not_sent_to_a_redirect_host(tmp_path):
    """A redirect to a CDN must not carry the Blackboard session cookie."""
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen[request.url.host] = request.headers.get("cookie")
        if request.url.host == "learn.example.edu":
            return httpx.Response(302, headers={"location": "https://cdn.other.com/f.pdf"})
        return httpx.Response(200, content=b"pdf")

    sm = _make_sm([{"name": "s_session_id", "value": "secret",
                    "domain": "learn.example.edu", "path": "/"}])
    real_client = httpx.Client
    with patch("bb.downloader.httpx.Client",
               lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)):
        Downloader(sm).download("https://learn.example.edu/bbcswebdav/f.pdf", tmp_path, "f.pdf")
    assert seen["learn.example.edu"] == "s_session_id=secret"
    assert seen["cdn.other.com"] is None
    assert (tmp_path / "f.pdf").read_bytes() == b"pdf"


def _legacy_notes(tmp_path):
    """A pre-migration-7 download: file on disk plus a row with url NULL."""
    db = Database(tmp_path / "bb.db")
    db.setup()
    dest = tmp_path / "d"
    dest.mkdir()
    f = dest / "Notes.pdf"
    f.write_bytes(b"x" * 2048)
    db.record_download("BTP200", "Notes.pdf", str(f), 2048, url=None)
    return db, dest


def test_legacy_download_is_adopted_not_duplicated(tmp_path):
    db, dest = _legacy_notes(tmp_path)
    url = "https://h/a/notes.pdf"
    item = ContentItem("file", "Notes", download_url=url)
    report = download_items([item], "BTP200", dest, _FakeDL(), db,
                            ambiguous_names=ambiguous_filenames([item]))
    assert report.saved == [] and report.skipped == ["Notes.pdf"]
    assert [p.name for p in dest.iterdir()] == ["Notes.pdf"]
    assert db.download_url_for_file("BTP200", "Notes.pdf") == url


def test_legacy_download_is_not_adopted_without_ambiguous_names(tmp_path):
    db, dest = _legacy_notes(tmp_path)
    item = ContentItem("file", "Notes", download_url="https://h/a/notes.pdf")
    report = download_items([item], "BTP200", dest, _FakeDL(), db)
    assert report.skipped == [] and len(report.saved) == 1
    assert db.download_url_for_file("BTP200", "Notes.pdf") is None


def test_legacy_not_adopted_by_narrowed_batch_when_name_ambiguous_in_tree(tmp_path):
    db, dest = _legacy_notes(tmp_path)  # legacy "Notes.pdf" (really week 4's)
    w4 = ContentItem("file", "Notes", download_url="https://h/w4/n.pdf")
    w5 = ContentItem("file", "Notes", download_url="https://h/w5/n.pdf")
    report = download_items([w5], "BTP200", dest, _FakeDL(), db,
                            ambiguous_names=ambiguous_filenames([w4, w5]))
    assert report.skipped == [] and len(report.saved) == 1
    assert report.saved[0].name != "Notes.pdf"
    assert db.download_url_for_file("BTP200", "Notes.pdf") is None


def test_ambiguous_filenames_returns_only_duplicates():
    a = ContentItem("file", "Notes", download_url="https://h/1/a.pdf")
    b = ContentItem("file", "Notes", download_url="https://h/2/b.pdf")
    c = ContentItem("file", "Other", download_url="https://h/3/c.pdf")
    folder = ContentItem("folder", "F", children=[b, c])
    assert ambiguous_filenames([a, folder]) == {"Notes.pdf"}


def test_legacy_download_is_not_adopted_when_batch_names_collide(tmp_path):
    db, dest = _legacy_notes(tmp_path)
    items = [ContentItem("file", "Notes", download_url="https://h/w1/n.pdf"),
             ContentItem("file", "Notes", download_url="https://h/w2/n.pdf")]
    report = download_items(items, "BTP200", dest, _FakeDL(), db)
    assert report.skipped == [] and len(report.saved) == 2
    assert all(p.name != "Notes.pdf" for p in report.saved)
    assert db.download_url_for_file("BTP200", "Notes.pdf") is None


def test_safe_filename_caps_stem_by_utf8_bytes():
    from bb.downloader import safe_filename
    name = safe_filename(ContentItem("file", "é" * 200, download_url="https://h/f.pdf"))
    stem = name[: -len(".pdf")]
    assert len(stem.encode("utf-8")) <= 150
    assert stem == "é" * 75
