"""Action tools: let chat/MCP fetch data itself instead of telling the student to run commands.

Sync and course scraping run in a subprocess. In-process they would print Rich output to
stdout, which corrupts the MCP stdio transport. Downloads run in-process (httpx, silent).
"""

from __future__ import annotations

import subprocess
import sys

import bb.config as _config_module
from bb.db import Database
from bb.tools.queries import get_recent_changes, resolve_course

_MAX_FILES_PER_CALL = 5


def _run_cli(*args: str, timeout: int) -> tuple[bool, str]:
    """Run `python -m bb.cli <args>`; return (ok, last few non-empty output lines)."""
    try:
        r = subprocess.run(
            # -P: the chat's cwd must not shadow the installed bb package.
            # stdin=DEVNULL: the child must never read the MCP stdio stream or wait on it.
            [sys.executable, "-P", "-m", "bb.cli", *args],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    lines = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip()]
    return r.returncode == 0, "\n".join(lines[-6:])


def sync_now(full: bool = False) -> dict:
    """Refresh Blackboard data right now, then report what changed.

    Use when the student asks to sync, refresh, or update, or when data looks stale
    (get_sync_status shows an old last_sync). The default is a fast deadline-only sync
    (a few seconds, no browser). Pass full=True only when grades or announcements are
    needed — it takes 1-2 minutes and needs a valid Blackboard login.
    """
    args = ("sync",) if full else ("sync", "--ical-only")
    ok, output = _run_cli(*args, timeout=600 if full else 120)
    return {"ok": ok, "full": full, "output": output, "recent_changes": get_recent_changes(days=1)}


def refresh_course_content(course: str) -> dict:
    """Fetch and cache a course's content list (modules, folders, files, links).

    Use when get_course_content or search_content returns nothing for a course, or the
    student says materials are missing. Takes 10-60 seconds. Afterwards, use
    search_content or download_course_file.
    """
    from bb.cache import load_tree

    code = resolve_course(course) or course.upper()
    ok, output = _run_cli("course", code, "--refresh", timeout=300)
    tree = load_tree(code)
    if not ok or tree is None:
        return {"ok": False, "course": code, "error": output or "scrape failed"}
    return {"ok": True, "course": code, "top_level_items": [i.title for i in tree.items]}


def download_course_file(course: str, name: str) -> dict:
    """Download course files whose title contains `name` (case-insensitive).

    Use when the student wants to read, summarize, or be quizzed on a file that
    list_downloaded_files does not show yet. A folder name (e.g. 'Week 5') downloads
    the files inside it. Downloads at most 5 files per call. Afterwards, call
    read_file_content with the same course and the downloaded filename.
    """
    from bb.cache import load_tree
    from bb.downloader import Downloader, collect_downloadable, download_items
    from bb.models.content import find_items
    from bb.security.session import SessionManager

    code = resolve_course(course) or course.upper()
    tree = load_tree(code)
    if tree is None:
        return {"ok": False, "course": code,
                "error": "course content not cached — call refresh_course_content first"}

    seen: set[str] = set()
    matches = []
    for item in collect_downloadable(find_items(tree.items, name)):
        if item.download_url not in seen:  # folder + its child can both match
            seen.add(item.download_url)
            matches.append(item)
    if not matches:
        return {"ok": False, "course": code, "error": f"no downloadable file matching '{name}'"}

    bb_dir = _config_module.BB_DIR
    with Database(bb_dir / "bb.db") as db:
        db.setup()
        report = download_items(
            matches[:_MAX_FILES_PER_CALL], code, bb_dir / "files" / code,
            Downloader(SessionManager(bb_dir / "session.enc")), db,
        )
    return {
        "ok": not report.failed,
        "course": code,
        "downloaded": [p.name for p in report.saved],
        "already_had": report.skipped,
        "failed": [f"{n}: {e}" for n, e in report.failed],
        "more_matches": max(0, len(matches) - _MAX_FILES_PER_CALL),
    }
