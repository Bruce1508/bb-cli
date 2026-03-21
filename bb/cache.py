from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import bb.config as _config_module
from bb.models.content import ContentTree, content_tree_from_dict, content_tree_to_dict

DEFAULT_TTL_HOURS = 2


def _cache_path(course_code: str) -> Path:
    # Resolve BB_DIR at call time — never at module level (frozen import-time value breaks tests)
    return _config_module.BB_DIR / "cache" / course_code.upper() / "tree.json"


def save_tree(tree: ContentTree) -> None:
    """Serialize ContentTree → JSON → ~/.bb/cache/<COURSE>/tree.json."""
    path = _cache_path(tree.course_code)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(content_tree_to_dict(tree), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_tree(course_code: str) -> ContentTree | None:
    """Load cached tree. Returns None if file missing or corrupt."""
    path = _cache_path(course_code)
    if not path.exists():
        return None
    try:
        return content_tree_from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, KeyError):
        return None  # Corrupt cache — treat as missing


def is_fresh(course_code: str, ttl_hours: int = DEFAULT_TTL_HOURS) -> bool:
    """Return True if cache exists and scraped_at is within TTL.

    ContentTree.scraped_at is a timezone-aware datetime — subtract directly from
    datetime.now(timezone.utc) without fromisoformat().
    """
    tree = load_tree(course_code)
    if tree is None:
        return False
    age_hours = (datetime.now(timezone.utc) - tree.scraped_at).total_seconds() / 3600
    return age_hours < ttl_hours


def clear(course_code: str | None = None) -> int:
    """Delete cache file(s). Returns number of courses cleared."""
    cache_dir = _config_module.BB_DIR / "cache"
    if course_code:
        path = _cache_path(course_code)
        if path.exists():
            path.unlink()
            return 1
        return 0
    # Clear all
    if not cache_dir.exists():
        return 0
    count = 0
    for course_dir in cache_dir.iterdir():
        tree_file = course_dir / "tree.json"
        if tree_file.exists():
            tree_file.unlink()
            count += 1
    return count
