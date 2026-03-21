"""
Tests for `bb download` and `bb open` commands in bb/cli.py

Strategy:
- Patch bb.config.BB_DIR → tmp_path
- Seed ContentTree via cache.save_tree (real cache layer)
- Mock Downloader.download to avoid real HTTP
- Mock webbrowser.open for bb open tests

Success criteria:
- bb download: no cache → exit 1 + message
- bb download --all: downloads all items with download_url
- bb download --type pdf: filters by extension
- bb download "name": filters by title substring
- bb download --dry-run: lists, no download
- bb open: no cache → exit 1
- bb open "item": calls webbrowser.open with item.url
- bb open "nonexistent": exit 1, lists items
- bb open item with url=None: exit 1, no URL message
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from bb.cache import save_tree
from bb.cli import app
from bb.models.content import ContentItem, ContentTree

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tree(items: list | None = None) -> ContentTree:
    return ContentTree(
        course_code="BTP200",
        course_bb_id="_773522_1",
        scraped_at=datetime.now(timezone.utc),
        items=items or [],
    )


def _pdf_item(title: str = "Syllabus", url: str = "https://bb.example.com/ultra/file") -> ContentItem:
    return ContentItem(
        type="file",
        title=title,
        url=url,
        download_url="https://bb.example.com/bbcswebdav/syllabus.pdf",
    )


def _html_item(title: str = "Zoom Link") -> ContentItem:
    return ContentItem(
        type="link",
        title=title,
        url="https://zoom.us/j/123",
        download_url="https://bb.example.com/bbcswebdav/zoom.html",
    )


def _discussion_item(title: str = "Forum Post") -> ContentItem:
    return ContentItem(
        type="discussion",
        title=title,
        url="https://bb.example.com/ultra/discuss/123",
        download_url=None,  # not downloadable
    )


def _no_url_item(title: str = "Broken Item") -> ContentItem:
    return ContentItem(type="file", title=title, url=None, download_url=None)


# ---------------------------------------------------------------------------
# bb download — no cache
# ---------------------------------------------------------------------------


def test_download_exits_1_when_no_cache(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        result = runner.invoke(app, ["download", "BTP200", "--all"])
    assert result.exit_code == 1


def test_download_prints_run_course_first_when_no_cache(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        result = runner.invoke(app, ["download", "BTP200", "--all"])
    assert "course" in result.output.lower() or "cache" in result.output.lower()


# ---------------------------------------------------------------------------
# bb download --all
# ---------------------------------------------------------------------------


def test_download_all_exits_0(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree([_pdf_item()]))
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.Downloader") as mock_dl_cls,
        patch("bb.cli.Database"),
    ):
        mock_dl = MagicMock()
        saved_path = tmp_path / "files" / "BTP200" / "Syllabus.pdf"
        saved_path.parent.mkdir(parents=True, exist_ok=True)
        saved_path.touch()
        mock_dl.download.return_value = saved_path
        mock_dl_cls.return_value = mock_dl
        result = runner.invoke(app, ["download", "BTP200", "--all"])
    assert result.exit_code == 0, result.output


def test_download_all_skips_items_without_download_url(tmp_path):
    """Items with download_url=None (discussions, modules) must be silently skipped."""
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree([_discussion_item(), _pdf_item()]))
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.Downloader") as mock_dl_cls,
        patch("bb.cli.Database"),
    ):
        mock_dl = MagicMock()
        saved_path = tmp_path / "files" / "BTP200" / "Syllabus.pdf"
        saved_path.parent.mkdir(parents=True, exist_ok=True)
        saved_path.touch()
        mock_dl.download.return_value = saved_path
        mock_dl_cls.return_value = mock_dl
        runner.invoke(app, ["download", "BTP200", "--all"])
    # download() called once (only pdf_item has download_url)
    assert mock_dl.download.call_count == 1


def test_download_all_shows_summary(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree([_pdf_item()]))
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.Downloader") as mock_dl_cls,
        patch("bb.cli.Database"),
    ):
        mock_dl = MagicMock()
        saved_path = tmp_path / "files" / "BTP200" / "Syllabus.pdf"
        saved_path.parent.mkdir(parents=True, exist_ok=True)
        saved_path.touch()
        mock_dl.download.return_value = saved_path
        mock_dl_cls.return_value = mock_dl
        result = runner.invoke(app, ["download", "BTP200", "--all"])
    assert "downloaded" in result.output.lower()


# ---------------------------------------------------------------------------
# bb download --type
# ---------------------------------------------------------------------------


def test_download_type_pdf_only_downloads_pdf(tmp_path):
    items = [_pdf_item("Syllabus"), _html_item("Zoom")]
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree(items))
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.Downloader") as mock_dl_cls,
        patch("bb.cli.Database"),
    ):
        mock_dl = MagicMock()
        saved_path = tmp_path / "files" / "BTP200" / "Syllabus.pdf"
        saved_path.parent.mkdir(parents=True, exist_ok=True)
        saved_path.touch()
        mock_dl.download.return_value = saved_path
        mock_dl_cls.return_value = mock_dl
        runner.invoke(app, ["download", "BTP200", "--all", "--type", "pdf"])
    assert mock_dl.download.call_count == 1


# ---------------------------------------------------------------------------
# bb download ITEM_NAME
# ---------------------------------------------------------------------------


def test_download_by_name_downloads_matching_item(tmp_path):
    items = [_pdf_item("Tentative Syllabus"), _pdf_item("Lab 1")]
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree(items))
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.Downloader") as mock_dl_cls,
        patch("bb.cli.Database"),
    ):
        mock_dl = MagicMock()
        saved_path = tmp_path / "files" / "BTP200" / "Tentative_Syllabus.pdf"
        saved_path.parent.mkdir(parents=True, exist_ok=True)
        saved_path.touch()
        mock_dl.download.return_value = saved_path
        mock_dl_cls.return_value = mock_dl
        runner.invoke(app, ["download", "BTP200", "Tentative"])
    assert mock_dl.download.call_count == 1


# ---------------------------------------------------------------------------
# bb download --dry-run
# ---------------------------------------------------------------------------


def test_download_dry_run_exits_0(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree([_pdf_item()]))
    with patch("bb.config.BB_DIR", tmp_path):
        result = runner.invoke(app, ["download", "BTP200", "--all", "--dry-run"])
    assert result.exit_code == 0


def test_download_dry_run_does_not_call_downloader(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree([_pdf_item()]))
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.Downloader") as mock_dl_cls,
    ):
        runner.invoke(app, ["download", "BTP200", "--all", "--dry-run"])
    mock_dl_cls.assert_not_called()


def test_download_dry_run_lists_files(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree([_pdf_item("Syllabus")]))
    with patch("bb.config.BB_DIR", tmp_path):
        result = runner.invoke(app, ["download", "BTP200", "--all", "--dry-run"])
    assert "Syllabus" in result.output


# ---------------------------------------------------------------------------
# bb download — already downloaded (skip)
# ---------------------------------------------------------------------------


def test_download_skips_already_downloaded_file(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree([_pdf_item("Syllabus")]))
    # Pre-create the file so it's "already downloaded"
    already = tmp_path / "files" / "BTP200" / "Syllabus.pdf"
    already.parent.mkdir(parents=True, exist_ok=True)
    already.write_bytes(b"existing")
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.Downloader") as mock_dl_cls,
    ):
        mock_dl = MagicMock()
        mock_dl_cls.return_value = mock_dl
        result = runner.invoke(app, ["download", "BTP200", "--all"])
    mock_dl.download.assert_not_called()
    assert "skip" in result.output.lower() or "⏩" in result.output


# ---------------------------------------------------------------------------
# bb open — happy path
# ---------------------------------------------------------------------------


def test_open_exits_0(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree([_pdf_item("Introduce Yourselves")]))
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.webbrowser.open"),
    ):
        result = runner.invoke(app, ["open", "BTP200", "Introduce"])
    assert result.exit_code == 0, result.output


def test_open_calls_webbrowser_open(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree([_pdf_item("Introduce Yourselves", url="https://bb.com/discuss")]))
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.webbrowser.open") as mock_wb,
    ):
        runner.invoke(app, ["open", "BTP200", "Introduce"])
    mock_wb.assert_called_once_with("https://bb.com/discuss")


def test_open_prints_url(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree([_pdf_item("Discussion", url="https://bb.com/forum")]))
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.webbrowser.open"),
    ):
        result = runner.invoke(app, ["open", "BTP200", "Discussion"])
    assert "https://bb.com/forum" in result.output


# ---------------------------------------------------------------------------
# bb open — error paths
# ---------------------------------------------------------------------------


def test_open_exits_1_when_no_cache(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        result = runner.invoke(app, ["open", "BTP200", "anything"])
    assert result.exit_code == 1


def test_open_exits_1_when_item_not_found(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree([_pdf_item("Syllabus")]))
    with patch("bb.config.BB_DIR", tmp_path):
        result = runner.invoke(app, ["open", "BTP200", "nonexistent_xyz"])
    assert result.exit_code == 1


def test_open_lists_available_items_when_not_found(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree([_pdf_item("Syllabus"), _pdf_item("Lab 1")]))
    with patch("bb.config.BB_DIR", tmp_path):
        result = runner.invoke(app, ["open", "BTP200", "nonexistent_xyz"])
    assert "Syllabus" in result.output or "Lab 1" in result.output


def test_open_exits_1_when_url_is_none(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree([_no_url_item("Broken")]))
    with patch("bb.config.BB_DIR", tmp_path):
        result = runner.invoke(app, ["open", "BTP200", "Broken"])
    assert result.exit_code == 1


def test_open_prints_no_url_message_when_url_none(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree([_no_url_item("Broken")]))
    with patch("bb.config.BB_DIR", tmp_path):
        result = runner.invoke(app, ["open", "BTP200", "Broken"])
    assert "no url" in result.output.lower() or "url" in result.output.lower()
