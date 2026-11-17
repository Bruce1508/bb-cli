import subprocess
from datetime import datetime, timezone
from unittest.mock import patch

from bb.cache import save_tree
from bb.db import Database
from bb.models.content import ContentItem, ContentTree
from bb.tools.actions import download_course_file, refresh_course_content, sync_now


def _ok(stdout="✔ 3 deadlines (1 new)\n"):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_sync_now_defaults_to_fast_ical_sync(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path), \
         patch("bb.tools.actions.subprocess.run", return_value=_ok()) as run:
        out = sync_now()
    assert run.call_args.args[0][-2:] == ["sync", "--ical-only"]
    assert out["ok"] is True and "3 deadlines" in out["output"]


def test_sync_now_full(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path), \
         patch("bb.tools.actions.subprocess.run", return_value=_ok()) as run:
        sync_now(full=True)
    assert run.call_args.args[0][-1] == "sync"


def test_sync_now_timeout_is_reported(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path), \
         patch("bb.tools.actions.subprocess.run",
               side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1)):
        out = sync_now()
    assert out["ok"] is False and "timed out" in out["output"]


def _tree(code="BTP200"):
    return ContentTree(code, "_1", datetime.now(timezone.utc), items=[
        ContentItem("folder", "Week 5", children=[
            ContentItem("file", "Week 5 Slides", download_url="https://h/w5.pptx"),
        ]),
        ContentItem("file", "Syllabus", download_url="https://h/syl.pdf"),
    ])


def test_refresh_course_content_reads_new_cache(tmp_path):
    def fake_run(*a, **kw):
        save_tree(_tree())
        return _ok()
    with patch("bb.config.BB_DIR", tmp_path), \
         patch("bb.tools.actions.subprocess.run", side_effect=fake_run) as run:
        out = refresh_course_content("btp200")
    assert run.call_args.args[0][-3:] == ["course", "BTP200", "--refresh"]
    assert out == {"ok": True, "course": "BTP200", "top_level_items": ["Week 5", "Syllabus"]}


def test_download_course_file_needs_cache(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        out = download_course_file("BTP200", "week 5")
    assert out["ok"] is False and "refresh_course_content" in out["error"]


def test_download_course_file_dedups_folder_and_child_match(tmp_path):
    def fake_download(self, url, dest_dir, filename):
        dest_dir.mkdir(parents=True, exist_ok=True)
        p = dest_dir / filename
        p.write_bytes(b"x")
        return p
    with patch("bb.config.BB_DIR", tmp_path):
        Database(tmp_path / "bb.db").setup()
        save_tree(_tree())
        with patch("bb.downloader.Downloader.download", fake_download):
            out = download_course_file("BTP200", "week 5")
    assert out["ok"] is True
    assert out["downloaded"] == ["Week 5 Slides.pptx"]  # folder + child matched, saved once
