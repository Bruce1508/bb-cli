from unittest.mock import patch

from bb.db import Database
from bb.tools.queries import search_file_text


def _seed(tmp_path, files: dict[str, str], course="BTP200"):
    d = tmp_path / "files" / course
    d.mkdir(parents=True, exist_ok=True)
    db = Database(tmp_path / "bb.db")
    db.setup()
    for name, text in files.items():
        (d / name).write_text(text)
        db.record_download(course, name, str(d / name), len(text))
    db.close()


def test_finds_phrase_with_page_and_snippet(tmp_path):
    _seed(tmp_path, {"week3.md": "Intro.\nRecursion is when a function calls itself.",
                     "week4.md": "Pointers and memory."})
    with patch("bb.config.BB_DIR", tmp_path):
        hits = search_file_text("recursion")
    assert len(hits) == 1
    assert hits[0]["filename"] == "week3.md" and hits[0]["page"] == 1
    assert "function calls itself" in hits[0]["snippet"]


def test_course_filter_and_empty_query(tmp_path):
    _seed(tmp_path, {"a.md": "recursion"}, course="BTP200")
    _seed(tmp_path, {"b.md": "recursion"}, course="WEB322")
    with patch("bb.config.BB_DIR", tmp_path):
        assert [h["course"] for h in search_file_text("recursion", course="WEB322")] == ["WEB322"]
        assert search_file_text("   ") == []


def test_hit_cap(tmp_path):
    _seed(tmp_path, {f"f{i}.md": "recursion" for i in range(15)})
    with patch("bb.config.BB_DIR", tmp_path):
        assert len(search_file_text("recursion")) == 10
