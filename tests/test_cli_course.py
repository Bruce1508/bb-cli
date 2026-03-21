"""
Tests for `bb course <COURSE>` and `bb cache-clear` commands in bb/cli.py

Strategy:
- Patch bb.config.BB_DIR → tmp_path (DB + cache both land in tmp_path)
- Seed course_map via db.upsert_course_map so bb_id lookup succeeds
- For cache-hit tests: save a real ContentTree via save_tree before invoking
- For stale-cache tests: save a tree with scraped_at 3h ago (> 2h TTL)
- For scrape-path tests: mock fetch_course_content to return a ContentTree (no Playwright)
- Never mock load_config by default — patch BB_DIR so load_config never finds a file
  and would fail; therefore patch bb.cli.load_config for all tests that reach the scrape path

Success criteria:
- bb course <COURSE>: exits 1 when course not in DB; prints "Run bb sync" message
- bb course <COURSE>: exits 0 when fresh cache hit; shows course code + item titles
- bb course <COURSE>: fresh cache → no stale warning in output
- bb course <COURSE>: stale cache → prints stale warning; still shows items
- bb course <COURSE> --refresh: scrapes even if fresh cache exists
- bb course <COURSE>: no cache → scrapes; prints scraping message
- bb course <COURSE> --tree: exits 0; shows course code
- bb cache-clear: no cache → "No cache to clear"; exits 0
- bb cache-clear <COURSE>: clears specific course; prints course name
- bb cache-clear (no arg): clears all; prints count
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from bb.cache import save_tree
from bb.cli import app
from bb.config import BBConfig, NotificationConfig
from bb.db import Database
from bb.models.content import ContentItem, ContentTree

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> BBConfig:
    return BBConfig(
        lms_type="blackboard_ultra",
        lms_url="https://learn.example.com",
        notification=NotificationConfig(provider="terminal"),
    )


def _make_tree(
    course_code: str = "BTP200",
    scraped_at: datetime | None = None,
    items: list | None = None,
) -> ContentTree:
    if scraped_at is None:
        scraped_at = datetime.now(timezone.utc)
    if items is None:
        items = [ContentItem(type="file", title="Lab 1.pdf")]
    return ContentTree(
        course_code=course_code,
        course_bb_id="_773522_1",
        scraped_at=scraped_at,
        items=items,
    )


def _fresh_tree(**kw) -> ContentTree:
    return _make_tree(scraped_at=datetime.now(timezone.utc) - timedelta(minutes=5), **kw)


def _stale_tree(**kw) -> ContentTree:
    return _make_tree(scraped_at=datetime.now(timezone.utc) - timedelta(hours=3), **kw)


def _seed_course(tmp_path, course_code: str = "BTP200", bb_id: str = "_773522_1") -> None:
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        db.upsert_course_map(course_code, bb_id)


def _invoke_course(tmp_path, *args):
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.load_config", return_value=_make_config()),
    ):
        return runner.invoke(app, ["course", *args])


def _invoke_cache_clear(tmp_path, *args):
    with patch("bb.config.BB_DIR", tmp_path):
        return runner.invoke(app, ["cache-clear", *args])


# ---------------------------------------------------------------------------
# bb course — course not in DB
# ---------------------------------------------------------------------------


def test_course_exits_1_when_course_not_in_db(tmp_path):
    # DB exists but course_map is empty
    with Database(tmp_path / "bb.db") as db:
        db.setup()
    result = _invoke_course(tmp_path, "BTP200")
    assert result.exit_code == 1


def test_course_prints_run_sync_when_not_in_db(tmp_path):
    with Database(tmp_path / "bb.db") as db:
        db.setup()
    result = _invoke_course(tmp_path, "BTP200")
    assert "sync" in result.output.lower()


def test_course_shows_course_code_in_not_found_message(tmp_path):
    with Database(tmp_path / "bb.db") as db:
        db.setup()
    result = _invoke_course(tmp_path, "BTP200")
    assert "BTP200" in result.output


# ---------------------------------------------------------------------------
# bb course — fresh cache hit
# ---------------------------------------------------------------------------


def test_course_exits_0_on_fresh_cache_hit(tmp_path):
    _seed_course(tmp_path)
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_fresh_tree())
    result = _invoke_course(tmp_path, "BTP200")
    assert result.exit_code == 0, result.output


def test_course_shows_course_code_on_cache_hit(tmp_path):
    _seed_course(tmp_path)
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_fresh_tree())
    result = _invoke_course(tmp_path, "BTP200")
    assert "BTP200" in result.output


def test_course_shows_item_title_on_cache_hit(tmp_path):
    _seed_course(tmp_path)
    tree = _fresh_tree(items=[ContentItem(type="file", title="Lecture Slides")])
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(tree)
    result = _invoke_course(tmp_path, "BTP200")
    assert "Lecture Slides" in result.output


def test_course_no_stale_warning_on_fresh_cache(tmp_path):
    _seed_course(tmp_path)
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_fresh_tree())
    result = _invoke_course(tmp_path, "BTP200")
    assert "stale" not in result.output.lower()


# ---------------------------------------------------------------------------
# bb course — stale cache
# ---------------------------------------------------------------------------


def test_course_exits_0_on_stale_cache(tmp_path):
    _seed_course(tmp_path)
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_stale_tree())
    result = _invoke_course(tmp_path, "BTP200")
    assert result.exit_code == 0, result.output


def test_course_shows_stale_warning_on_stale_cache(tmp_path):
    _seed_course(tmp_path)
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_stale_tree())
    result = _invoke_course(tmp_path, "BTP200")
    assert "stale" in result.output.lower()


def test_course_still_shows_items_on_stale_cache(tmp_path):
    _seed_course(tmp_path)
    tree = _stale_tree(items=[ContentItem(type="file", title="Old Notes")])
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(tree)
    result = _invoke_course(tmp_path, "BTP200")
    assert "Old Notes" in result.output


# ---------------------------------------------------------------------------
# bb course — no cache (scrape path)
# ---------------------------------------------------------------------------


def test_course_prints_scraping_message_when_no_cache(tmp_path):
    _seed_course(tmp_path)
    scraped_tree = _fresh_tree(items=[ContentItem(type="file", title="Scraped Item")])
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.load_config", return_value=_make_config()),
        patch(
            "bb.adapters.blackboard_ultra.BlackboardUltraAdapter.fetch_course_content",
            return_value=scraped_tree,
        ),
        patch("bb.security.session.SessionManager"),
    ):
        result = runner.invoke(app, ["course", "BTP200"])
    assert "scraping" in result.output.lower() or "⟳" in result.output


def test_course_exits_0_after_successful_scrape(tmp_path):
    _seed_course(tmp_path)
    scraped_tree = _fresh_tree()
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.load_config", return_value=_make_config()),
        patch(
            "bb.adapters.blackboard_ultra.BlackboardUltraAdapter.fetch_course_content",
            return_value=scraped_tree,
        ),
        patch("bb.security.session.SessionManager"),
    ):
        result = runner.invoke(app, ["course", "BTP200"])
    assert result.exit_code == 0, result.output


def test_course_shows_scraped_item_title(tmp_path):
    _seed_course(tmp_path)
    scraped_tree = _fresh_tree(items=[ContentItem(type="file", title="Fresh Content")])
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.load_config", return_value=_make_config()),
        patch(
            "bb.adapters.blackboard_ultra.BlackboardUltraAdapter.fetch_course_content",
            return_value=scraped_tree,
        ),
        patch("bb.security.session.SessionManager"),
    ):
        result = runner.invoke(app, ["course", "BTP200"])
    assert "Fresh Content" in result.output


# ---------------------------------------------------------------------------
# bb course --refresh forces scrape
# ---------------------------------------------------------------------------


def test_course_refresh_scrapes_even_with_fresh_cache(tmp_path):
    """--refresh must bypass cache and call fetch_course_content."""
    _seed_course(tmp_path)
    scraped_tree = _fresh_tree(items=[ContentItem(type="file", title="Refreshed")])
    mock_fetch = MagicMock(return_value=scraped_tree)
    with (
        patch("bb.config.BB_DIR", tmp_path),
        patch("bb.cli.load_config", return_value=_make_config()),
        patch(
            "bb.adapters.blackboard_ultra.BlackboardUltraAdapter.fetch_course_content",
            mock_fetch,
        ),
        patch("bb.security.session.SessionManager"),
    ):
        # save a fresh cache first
        save_tree(_fresh_tree())
        result = runner.invoke(app, ["course", "BTP200", "--refresh"])
    mock_fetch.assert_called_once()
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# bb course --tree flag
# ---------------------------------------------------------------------------


def test_course_tree_flag_exits_0(tmp_path):
    _seed_course(tmp_path)
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_fresh_tree())
    result = _invoke_course(tmp_path, "BTP200", "--tree")
    assert result.exit_code == 0, result.output


def test_course_tree_flag_shows_course_code(tmp_path):
    _seed_course(tmp_path)
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_fresh_tree())
    result = _invoke_course(tmp_path, "BTP200", "--tree")
    assert "BTP200" in result.output


def test_course_tree_flag_shows_item_title(tmp_path):
    _seed_course(tmp_path)
    tree = _fresh_tree(items=[ContentItem(type="module", title="Week 1 Module")])
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(tree)
    result = _invoke_course(tmp_path, "BTP200", "--tree")
    assert "Week 1 Module" in result.output


# ---------------------------------------------------------------------------
# bb course — case insensitivity
# ---------------------------------------------------------------------------


def test_course_lowercase_code_is_accepted(tmp_path):
    _seed_course(tmp_path, "BTP200")
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_fresh_tree())
    result = _invoke_course(tmp_path, "btp200")
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# bb cache-clear
# ---------------------------------------------------------------------------


def test_cache_clear_exits_0_when_no_cache(tmp_path):
    result = _invoke_cache_clear(tmp_path)
    assert result.exit_code == 0, result.output


def test_cache_clear_prints_no_cache_message_when_empty(tmp_path):
    result = _invoke_cache_clear(tmp_path)
    assert "no cache" in result.output.lower()


def test_cache_clear_course_exits_0(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_fresh_tree())
    result = _invoke_cache_clear(tmp_path, "BTP200")
    assert result.exit_code == 0, result.output


def test_cache_clear_course_prints_course_name(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_fresh_tree())
    result = _invoke_cache_clear(tmp_path, "BTP200")
    assert "BTP200" in result.output


def test_cache_clear_course_removes_cache_file(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_fresh_tree())
        _invoke_cache_clear(tmp_path, "BTP200")
    assert not (tmp_path / "cache" / "BTP200" / "tree.json").exists()


def test_cache_clear_all_prints_count(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_fresh_tree(course_code="BTP200"))
        save_tree(_fresh_tree(course_code="BTI325"))
    result = _invoke_cache_clear(tmp_path)
    assert "2" in result.output


def test_cache_clear_all_removes_all_files(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_fresh_tree(course_code="BTP200"))
        save_tree(_fresh_tree(course_code="BTI325"))
        _invoke_cache_clear(tmp_path)
    assert not (tmp_path / "cache" / "BTP200" / "tree.json").exists()
    assert not (tmp_path / "cache" / "BTI325" / "tree.json").exists()


def test_cache_clear_course_returns_no_cache_when_already_cleared(tmp_path):
    result = _invoke_cache_clear(tmp_path, "BTP200")
    assert "no cache" in result.output.lower()
