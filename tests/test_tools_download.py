"""
Tests for list_downloaded_files + read_file_content tool functions.

Strategy:
- list_downloaded_files: real SQLite (tmp_path) + patch BB_DIR
- read_file_content: mock pdfplumber.open — no real PDF needed
- Test error paths: missing dir, not PDF, pdfplumber exception
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bb.db import Database
from bb.tools.queries import list_downloaded_files, read_file_content


# ---------------------------------------------------------------------------
# list_downloaded_files
# ---------------------------------------------------------------------------


def test_list_downloaded_files_returns_list(tmp_path):
    with Database(tmp_path / "bb.db") as db:
        db.setup()
    with patch("bb.config.BB_DIR", tmp_path):
        result = list_downloaded_files()
    assert isinstance(result, list)


def test_list_downloaded_files_empty_when_no_downloads(tmp_path):
    with Database(tmp_path / "bb.db") as db:
        db.setup()
    with patch("bb.config.BB_DIR", tmp_path):
        result = list_downloaded_files()
    assert result == []


def test_list_downloaded_files_returns_all(tmp_path):
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        db.record_download("BTP200", "a.pdf", "/a", 100)
        db.record_download("BTI325", "b.pdf", "/b", 200)
    with patch("bb.config.BB_DIR", tmp_path):
        result = list_downloaded_files()
    assert len(result) == 2


def test_list_downloaded_files_filters_by_course(tmp_path):
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        db.record_download("BTP200", "a.pdf", "/a", 100)
        db.record_download("BTI325", "b.pdf", "/b", 200)
    with patch("bb.config.BB_DIR", tmp_path):
        result = list_downloaded_files(course="BTP200")
    assert len(result) == 1
    assert result[0]["course"] == "BTP200"


def test_list_downloaded_files_returns_empty_when_no_db(tmp_path):
    """Graceful degradation — no DB should return [] not crash."""
    with patch("bb.config.BB_DIR", tmp_path):
        result = list_downloaded_files()
    assert result == []


def test_list_downloaded_files_has_required_keys(tmp_path):
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        db.record_download("BTP200", "a.pdf", "/a", 100)
    with patch("bb.config.BB_DIR", tmp_path):
        result = list_downloaded_files()
    assert set(result[0].keys()) == {"course", "filename", "path", "size_bytes", "downloaded_at"}


# ---------------------------------------------------------------------------
# read_file_content
# ---------------------------------------------------------------------------


def _make_pdf_mock(text: str = "Hello World", pages: int = 1) -> MagicMock:
    """Return a mock pdfplumber PDF context manager."""
    mock_page = MagicMock()
    mock_page.extract_text.return_value = text
    mock_pdf = MagicMock()
    mock_pdf.__enter__ = lambda s: s
    mock_pdf.__exit__ = MagicMock(return_value=False)
    mock_pdf.pages = [mock_page] * pages
    return mock_pdf


def test_read_file_content_returns_dict(tmp_path):
    pdf_path = tmp_path / "files" / "BTP200"
    pdf_path.mkdir(parents=True)
    (pdf_path / "syllabus.pdf").touch()

    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.tools.queries.pdfplumber.open", return_value=_make_pdf_mock("Course content")),
    ):
        result = read_file_content("BTP200", "syllabus")
    assert isinstance(result, dict)


def test_read_file_content_returns_text(tmp_path):
    pdf_path = tmp_path / "files" / "BTP200"
    pdf_path.mkdir(parents=True)
    (pdf_path / "syllabus.pdf").touch()

    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.tools.queries.pdfplumber.open", return_value=_make_pdf_mock("My syllabus")),
    ):
        result = read_file_content("BTP200", "syllabus")
    assert result["text"] == "My syllabus"


def test_read_file_content_has_required_keys(tmp_path):
    pdf_path = tmp_path / "files" / "BTP200"
    pdf_path.mkdir(parents=True)
    (pdf_path / "syllabus.pdf").touch()

    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.tools.queries.pdfplumber.open", return_value=_make_pdf_mock()),
    ):
        result = read_file_content("BTP200", "syllabus")
    for key in ("filename", "course", "text", "pages", "char_count", "truncated"):
        assert key in result


def test_read_file_content_page_count_correct(tmp_path):
    pdf_path = tmp_path / "files" / "BTP200"
    pdf_path.mkdir(parents=True)
    (pdf_path / "syllabus.pdf").touch()

    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.tools.queries.pdfplumber.open", return_value=_make_pdf_mock("text", pages=3)),
    ):
        result = read_file_content("BTP200", "syllabus")
    assert result["pages"] == 3


def test_read_file_content_truncates_at_8000_chars(tmp_path):
    pdf_path = tmp_path / "files" / "BTP200"
    pdf_path.mkdir(parents=True)
    (pdf_path / "syllabus.pdf").touch()
    long_text = "x" * 10_000

    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.tools.queries.pdfplumber.open", return_value=_make_pdf_mock(long_text)),
    ):
        result = read_file_content("BTP200", "syllabus")
    assert len(result["text"]) == 8000
    assert result["truncated"] is True
    assert result["char_count"] == 10_000


def test_read_file_content_not_truncated_when_short(tmp_path):
    pdf_path = tmp_path / "files" / "BTP200"
    pdf_path.mkdir(parents=True)
    (pdf_path / "syllabus.pdf").touch()

    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.tools.queries.pdfplumber.open", return_value=_make_pdf_mock("short")),
    ):
        result = read_file_content("BTP200", "syllabus")
    assert result["truncated"] is False


def test_read_file_content_error_when_dir_missing(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        result = read_file_content("BTP200", "syllabus.pdf")
    assert "error" in result
    assert result["error"] == "file not found"


def test_read_file_content_error_when_file_not_found(tmp_path):
    pdf_path = tmp_path / "files" / "BTP200"
    pdf_path.mkdir(parents=True)
    # Dir exists but no matching file
    with patch("bb.config.BB_DIR", tmp_path):
        result = read_file_content("BTP200", "nonexistent")
    assert result["error"] == "file not found"


def test_read_file_content_error_when_not_pdf(tmp_path):
    pdf_path = tmp_path / "files" / "BTP200"
    pdf_path.mkdir(parents=True)
    (pdf_path / "notes.docx").touch()

    with patch("bb.config.BB_DIR", tmp_path):
        result = read_file_content("BTP200", "notes")
    assert result["error"] == "not a PDF"


def test_read_file_content_error_when_pdfplumber_raises(tmp_path):
    pdf_path = tmp_path / "files" / "BTP200"
    pdf_path.mkdir(parents=True)
    (pdf_path / "corrupt.pdf").touch()

    broken_mock = MagicMock()
    broken_mock.__enter__ = MagicMock(side_effect=Exception("bad PDF"))
    broken_mock.__exit__ = MagicMock(return_value=False)

    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.tools.queries.pdfplumber.open", return_value=broken_mock),
    ):
        result = read_file_content("BTP200", "corrupt")
    assert "unreadable" in result["error"]


def test_read_file_content_case_insensitive_course(tmp_path):
    pdf_path = tmp_path / "files" / "BTP200"
    pdf_path.mkdir(parents=True)
    (pdf_path / "notes.pdf").touch()

    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.tools.queries.pdfplumber.open", return_value=_make_pdf_mock("content")),
    ):
        result = read_file_content("btp200", "notes")
    assert result["course"] == "BTP200"
