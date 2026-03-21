"""
Tests for bb/cache.py — save_tree, load_tree, is_fresh, clear

Strategy:
- Patch bb.config.BB_DIR → tmp_path so ALL cache operations go to the test directory
- Use real filesystem (tmp_path) — cache is file-based, mocking it would test nothing
- Control time via scraped_at datetime (stale = 3h ago, fresh = 1m ago)

Success criteria:
- save_tree: writes JSON to correct path, creates parent dirs
- load_tree: returns ContentTree on hit, None on miss, None on corrupt JSON
- is_fresh: False when no cache; True when scraped < TTL ago; False when scraped > TTL ago
- clear(course): removes one course file, returns 1; no-op returns 0
- clear(None): removes all trees, returns count, handles missing cache dir
- clear cleans up now-empty course directories
- _cache_path always uppercases the course code
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from bb.cache import DEFAULT_TTL_HOURS, clear, is_fresh, load_tree, save_tree
from bb.models.content import ContentItem, ContentTree

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_tree(
    course_code: str = "BTP200",
    bb_id: str = "_773522_1",
    scraped_at: datetime | None = None,
    items: list | None = None,
) -> ContentTree:
    if scraped_at is None:
        scraped_at = datetime.now(timezone.utc)
    return ContentTree(
        course_code=course_code,
        course_bb_id=bb_id,
        scraped_at=scraped_at,
        items=items or [],
    )


def _fresh_tree(**kwargs) -> ContentTree:
    return _make_tree(scraped_at=datetime.now(timezone.utc) - timedelta(minutes=5), **kwargs)


def _stale_tree(**kwargs) -> ContentTree:
    return _make_tree(scraped_at=datetime.now(timezone.utc) - timedelta(hours=3), **kwargs)


# ---------------------------------------------------------------------------
# save_tree
# ---------------------------------------------------------------------------


def test_save_tree_creates_file(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree())
    assert (tmp_path / "cache" / "BTP200" / "tree.json").exists()


def test_save_tree_creates_parent_directories(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree(course_code="BTI325"))
    assert (tmp_path / "cache" / "BTI325").is_dir()


def test_save_tree_writes_valid_json(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree())
    path = tmp_path / "cache" / "BTP200" / "tree.json"
    data = json.loads(path.read_text())
    assert isinstance(data, dict)


def test_save_tree_json_has_required_keys(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree())
    path = tmp_path / "cache" / "BTP200" / "tree.json"
    data = json.loads(path.read_text())
    assert "course_code" in data
    assert "course_bb_id" in data
    assert "scraped_at" in data
    assert "items" in data


def test_save_tree_json_scraped_at_is_string(tmp_path):
    """scraped_at must be serialized to a string — not a raw datetime object."""
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree())
    path = tmp_path / "cache" / "BTP200" / "tree.json"
    data = json.loads(path.read_text())
    assert isinstance(data["scraped_at"], str)


def test_save_tree_uppercases_course_code_in_path(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree(course_code="btp200"))
    # Path must use uppercase regardless of input
    assert (tmp_path / "cache" / "BTP200" / "tree.json").exists()


def test_save_tree_overwrites_existing_cache(tmp_path):
    tree1 = _make_tree(bb_id="_old_1")
    tree2 = _make_tree(bb_id="_new_1")
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(tree1)
        save_tree(tree2)
    path = tmp_path / "cache" / "BTP200" / "tree.json"
    data = json.loads(path.read_text())
    assert data["course_bb_id"] == "_new_1"


# ---------------------------------------------------------------------------
# load_tree
# ---------------------------------------------------------------------------


def test_load_tree_returns_none_when_no_file(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        result = load_tree("BTP200")
    assert result is None


def test_load_tree_returns_content_tree_on_hit(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree())
        result = load_tree("BTP200")
    assert isinstance(result, ContentTree)


def test_load_tree_preserves_course_code(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree(course_code="BTP200"))
        result = load_tree("BTP200")
    assert result.course_code == "BTP200"


def test_load_tree_preserves_bb_id(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree(bb_id="_773522_1"))
        result = load_tree("BTP200")
    assert result.course_bb_id == "_773522_1"


def test_load_tree_scraped_at_is_datetime(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree())
        result = load_tree("BTP200")
    assert isinstance(result.scraped_at, datetime)


def test_load_tree_scraped_at_is_timezone_aware(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree())
        result = load_tree("BTP200")
    assert result.scraped_at.tzinfo is not None


def test_load_tree_preserves_items(tmp_path):
    item = ContentItem(type="file", title="Lab 1.pdf")
    tree = _make_tree(items=[item])
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(tree)
        result = load_tree("BTP200")
    assert len(result.items) == 1
    assert result.items[0].title == "Lab 1.pdf"


def test_load_tree_returns_none_on_corrupt_json(tmp_path):
    path = tmp_path / "cache" / "BTP200" / "tree.json"
    path.parent.mkdir(parents=True)
    path.write_text("not valid json", encoding="utf-8")
    with patch("bb.config.BB_DIR", tmp_path):
        result = load_tree("BTP200")
    assert result is None


def test_load_tree_returns_none_on_missing_key(tmp_path):
    """JSON that is valid but missing required keys → treated as corrupt → None."""
    path = tmp_path / "cache" / "BTP200" / "tree.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"course_code": "BTP200"}', encoding="utf-8")
    with patch("bb.config.BB_DIR", tmp_path):
        result = load_tree("BTP200")
    assert result is None


def test_load_tree_is_case_insensitive(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree(course_code="BTP200"))
        result = load_tree("btp200")
    assert result is not None


# ---------------------------------------------------------------------------
# is_fresh
# ---------------------------------------------------------------------------


def test_is_fresh_returns_false_when_no_cache(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        assert is_fresh("BTP200") is False


def test_is_fresh_returns_true_when_scraped_recently(tmp_path):
    """Scraped 5 minutes ago is within the 2-hour TTL."""
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_fresh_tree())
        assert is_fresh("BTP200") is True


def test_is_fresh_returns_false_when_scraped_3h_ago(tmp_path):
    """Scraped 3 hours ago exceeds the 2-hour default TTL."""
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_stale_tree())
        assert is_fresh("BTP200") is False


def test_is_fresh_respects_custom_ttl(tmp_path):
    """Custom ttl_hours=1 makes a 90-minute-old cache stale."""
    scraped_at = datetime.now(timezone.utc) - timedelta(minutes=90)
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree(scraped_at=scraped_at))
        assert is_fresh("BTP200", ttl_hours=1) is False
        assert is_fresh("BTP200", ttl_hours=3) is True


def test_is_fresh_boundary_just_under_ttl(tmp_path):
    """Scraped just under 2h ago is still fresh."""
    scraped_at = datetime.now(timezone.utc) - timedelta(hours=DEFAULT_TTL_HOURS, seconds=-60)
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree(scraped_at=scraped_at))
        assert is_fresh("BTP200") is True


def test_is_fresh_boundary_just_over_ttl(tmp_path):
    """Scraped just over 2h ago is stale."""
    scraped_at = datetime.now(timezone.utc) - timedelta(hours=DEFAULT_TTL_HOURS, seconds=60)
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree(scraped_at=scraped_at))
        assert is_fresh("BTP200") is False


# ---------------------------------------------------------------------------
# clear — single course
# ---------------------------------------------------------------------------


def test_clear_course_returns_1_when_cache_exists(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree())
        count = clear("BTP200")
    assert count == 1


def test_clear_course_removes_file(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree())
        clear("BTP200")
    assert not (tmp_path / "cache" / "BTP200" / "tree.json").exists()


def test_clear_course_returns_0_when_not_cached(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        count = clear("BTP200")
    assert count == 0


def test_clear_course_only_removes_specified_course(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree(course_code="BTP200"))
        save_tree(_make_tree(course_code="BTI325"))
        clear("BTP200")
    assert (tmp_path / "cache" / "BTI325" / "tree.json").exists()


def test_clear_course_file_is_gone_after_clear(tmp_path):
    """Single-course clear removes the tree.json file (directory cleanup is done by clear-all)."""
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree())
        clear("BTP200")
    assert not (tmp_path / "cache" / "BTP200" / "tree.json").exists()


# ---------------------------------------------------------------------------
# clear — all courses
# ---------------------------------------------------------------------------


def test_clear_all_returns_zero_when_no_cache_dir(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        count = clear()
    assert count == 0


def test_clear_all_returns_count_of_cleared_courses(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree(course_code="BTP200"))
        save_tree(_make_tree(course_code="BTI325"))
        count = clear()
    assert count == 2


def test_clear_all_removes_all_tree_files(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        save_tree(_make_tree(course_code="BTP200"))
        save_tree(_make_tree(course_code="BTI325"))
        clear()
    assert not (tmp_path / "cache" / "BTP200" / "tree.json").exists()
    assert not (tmp_path / "cache" / "BTI325" / "tree.json").exists()


def test_clear_all_returns_0_on_empty_cache_dir(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    with patch("bb.config.BB_DIR", tmp_path):
        count = clear()
    assert count == 0
