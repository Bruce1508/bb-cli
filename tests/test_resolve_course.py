from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from bb.adapters.base import Deadline
from bb.db import Database
from bb.tools.queries import get_upcoming_deadlines, resolve_course


@pytest.fixture
def courses(tmp_path):
    db = Database(tmp_path / "bb.db")
    db.setup()
    db.upsert_course_map("BTP200", "_1", "Object-Oriented Software Development")
    db.upsert_course_map("WEB322", "_2", "Web Programming Tools and Frameworks")
    db.upsert_course_map("WEB422", "_3", "Web Programming for Apps and Services")
    db.upsert_deadline(Deadline("d1", "BTP200", "Lab 4",
                                datetime.now(timezone.utc) + timedelta(days=1), "ical"))
    db.close()
    with patch("bb.config.BB_DIR", tmp_path):
        yield


@pytest.mark.parametrize("text,expected", [
    ("BTP200", "BTP200"),
    ("btp200", "BTP200"),
    ("btp", "BTP200"),            # unique code prefix
    ("object", "BTP200"),         # display-name match
    ("frameworks", "WEB322"),
    ("web programming tools", "WEB322"),
    ("xyz", "XYZ"),               # unknown → sanitized upper, so filters return nothing
    ("all", None),
    ("  ", None),
    (None, None),
])
def test_resolve_course(courses, text, expected):
    assert resolve_course(text) == expected


@pytest.mark.parametrize("text", ["web", "programming"])  # code hits / display-name hits
def test_ambiguous_course_is_an_error_naming_the_candidates(courses, text):
    with pytest.raises(ValueError, match="WEB322") as exc:
        resolve_course(text)
    assert "WEB422" in str(exc.value)


def test_tools_accept_loose_course_names(courses):
    assert [d["title"] for d in get_upcoming_deadlines(course="btp")] == ["Lab 4"]
    with pytest.raises(ValueError, match="Ambiguous"):
        get_upcoming_deadlines(course="web")


def test_every_course_tool_reports_ambiguity(courses):
    """No tool may swallow the ambiguity into an empty answer ("no deadlines")."""
    from bb.tools.ai_tools import (
        estimate_study_time,
        extract_key_concepts,
        generate_study_plan,
        summarize_content,
    )
    from bb.tools.queries import list_downloaded_files
    for call in (
        lambda: list_downloaded_files(course="web"),
        lambda: generate_study_plan(course="web"),
        lambda: extract_key_concepts(course="web"),
        lambda: estimate_study_time(course="web"),
        lambda: summarize_content(course="web", filename="x"),
    ):
        with pytest.raises(ValueError, match="Ambiguous"):
            call()


def test_dispatch_tool_returns_the_ambiguity_to_the_model(courses):
    import json

    from bb.ai.chat import dispatch_tool
    out = json.loads(dispatch_tool("get_grades", {"course": "web"}))
    assert "Ambiguous course 'web'" in out["error"] and "WEB422" in out["error"]


def test_cli_course_option_reports_ambiguity(tmp_path, courses):
    from typer.testing import CliRunner

    from bb.cli import app
    result = CliRunner().invoke(app, ["due", "--course", "web"])
    assert result.exit_code == 1
    assert "Ambiguous" in result.output and "WEB322" in result.output


def test_unmatched_course_cannot_become_a_path(courses):
    code = resolve_course("../../x")
    assert code and "/" not in code and "." not in code


def test_read_file_content_cannot_escape_bb_dir(tmp_path):
    from bb.tools.queries import read_file_content

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "f.pdf").write_bytes(b"%PDF secret")
    (tmp_path / "bb" / "files").mkdir(parents=True)  # as in a real ~/.bb
    with patch("bb.config.BB_DIR", tmp_path / "bb"), \
         patch("bb.text_extract.pdfplumber.open") as opened:
        result = read_file_content("../../outside", "f")
    assert "error" in result
    opened.assert_not_called()


def test_resolve_course_ambiguity_uses_sanitized_text(courses):
    with pytest.raises(ValueError, match="WEB322"):
        resolve_course("web?")
    assert resolve_course("btp!") == "BTP200"


def _seed_codes(tmp_path, codes):
    db = Database(tmp_path / "bb.db")
    db.setup()
    for i, c in enumerate(codes):
        db.upsert_course_map(c, f"_{i}")
    db.close()


@pytest.mark.parametrize("codes,text,expected", [
    (["BTP200NAA", "BTP200NAAL"], "btp200", "BTP200NAA"),  # lecture prefixes its lab
    (["ABC100", "ABC100L", "ABC100X"], "abc", "ABC100"),
])
def test_code_that_prefixes_every_other_hit_wins(tmp_path, codes, text, expected):
    _seed_codes(tmp_path, codes)
    with patch("bb.config.BB_DIR", tmp_path):
        assert resolve_course(text) == expected


@pytest.mark.parametrize("codes,text", [
    (["BTI425NAA", "BTP200NAA"], "BT"),
    (["ABC100L", "ABC100X"], "abc"),
])
def test_no_common_prefix_code_is_still_ambiguous(tmp_path, codes, text):
    _seed_codes(tmp_path, codes)
    with patch("bb.config.BB_DIR", tmp_path), pytest.raises(ValueError, match="Ambiguous"):
        resolve_course(text)


@pytest.mark.parametrize("text", [
    "all!", "any.", "a ll", "!!!", "*?", "null;", "xyz", "btp", "BTP200", "object", "frameworks",
])
def test_resolve_course_is_idempotent(courses, text):
    """Callers resolve once and pass the code on; a second resolve must not widen it.

    'all!' used to sanitize to 'ALL', which a second resolve read as "no filter".
    """
    once = resolve_course(text)
    assert once is not None
    assert resolve_course(once) == once


@pytest.mark.parametrize("text", ["all", "all!", "!!!", "*"])
def test_study_plan_never_spans_every_course(courses, text):
    from bb.tools.ai_tools import generate_study_plan
    plan = generate_study_plan(text)
    assert plan["upcoming_deadlines"] == []  # BTP200's Lab 4 must not leak in


@pytest.mark.parametrize("text", ["all", "all!", "!!!"])
def test_action_tools_refuse_a_non_course(courses, text):
    from unittest.mock import patch as _patch

    from bb.tools import actions
    with _patch.object(actions, "_run_cli") as run:
        assert actions.refresh_course_content(text)["ok"] is False
        assert actions.download_course_file(text, "slides")["ok"] is False
    run.assert_not_called()
