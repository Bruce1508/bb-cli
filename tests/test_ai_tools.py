"""Tests for bb/tools/ai_tools.py"""
from __future__ import annotations

from unittest.mock import patch

from bb.tools.ai_tools import (
    estimate_study_time,
    extract_key_concepts,
    generate_study_plan,
    summarize_content,
)

MOCK_GRADES = [{"course": "BTI325", "item": "Lab 1", "score": 18.0, "out_of": 20.0, "status": "graded"}]
MOCK_DEADLINES = [{"course": "BTI325", "title": "Lab 2", "due_at": "2026-04-01T12:00:00+00:00", "when": "due in 4 days", "source": "ical"}]
MOCK_FILES = [{"course": "BTI325", "filename": "syllabus.pdf", "path": "/tmp/syllabus.pdf"}]
MOCK_CONTENT_TREE = {
    "course_code": "BTI325",
    "scraped_at": "2026-03-28T00:00:00",
    "items": [
        {"title": "Lecture 1", "type": "file", "url": "https://bb.example.com/l1", "children": []},
        {"title": "Module 1", "type": "module", "url": None, "children": [
            {"title": "Quiz 1", "type": "file", "url": "https://bb.example.com/q1", "children": []}
        ]},
    ],
}
MOCK_FILE_CONTENT = {"filename": "syllabus.pdf", "course": "BTI325", "text": "Course overview", "pages": 3, "char_count": 15, "truncated": False}
MOCK_FILE_ERROR = {"error": "file not found"}


# ---------------------------------------------------------------------------
# summarize_content
# ---------------------------------------------------------------------------

def test_summarize_passes_through_success_result():
    with patch("bb.tools.ai_tools.read_file_content", return_value=MOCK_FILE_CONTENT):
        result = summarize_content(course="BTI325", filename="syllabus.pdf")
    assert result == MOCK_FILE_CONTENT


def test_summarize_passes_through_error_dict():
    with patch("bb.tools.ai_tools.read_file_content", return_value=MOCK_FILE_ERROR):
        result = summarize_content(course="BTI325", filename="missing.pdf")
    assert result == {"error": "file not found"}


def test_summarize_calls_read_file_content_with_correct_args():
    with patch("bb.tools.ai_tools.read_file_content", return_value=MOCK_FILE_CONTENT) as mock_fn:
        summarize_content(course="BTP200", filename="week3.pdf")
    mock_fn.assert_called_once_with(course="BTP200", filename="week3.pdf")


def test_summarize_passes_through_not_a_pdf_error():
    with patch("bb.tools.ai_tools.read_file_content", return_value={"error": "not a PDF"}):
        result = summarize_content(course="BTI325", filename="notes.docx")
    assert result["error"] == "not a PDF"


# ---------------------------------------------------------------------------
# generate_study_plan
# ---------------------------------------------------------------------------

def test_generate_study_plan_returns_dict():
    with patch("bb.tools.ai_tools.get_grades", return_value=[]), \
         patch("bb.tools.ai_tools.get_upcoming_deadlines", return_value=[]), \
         patch("bb.tools.ai_tools.list_downloaded_files", return_value=[]), \
         patch("bb.tools.ai_tools.get_course_content", return_value={}):
        result = generate_study_plan(course="BTI325")
    assert isinstance(result, dict)


def test_generate_study_plan_has_required_keys():
    with patch("bb.tools.ai_tools.get_grades", return_value=[]), \
         patch("bb.tools.ai_tools.get_upcoming_deadlines", return_value=[]), \
         patch("bb.tools.ai_tools.list_downloaded_files", return_value=[]), \
         patch("bb.tools.ai_tools.get_course_content", return_value={}):
        result = generate_study_plan(course="BTI325")
    for key in ("course", "exam_type", "grades", "upcoming_deadlines", "available_files", "content_tree"):
        assert key in result


def test_generate_study_plan_course_uppercased():
    with patch("bb.tools.ai_tools.get_grades", return_value=[]), \
         patch("bb.tools.ai_tools.get_upcoming_deadlines", return_value=[]), \
         patch("bb.tools.ai_tools.list_downloaded_files", return_value=[]), \
         patch("bb.tools.ai_tools.get_course_content", return_value={}):
        result = generate_study_plan(course="bti325")
    assert result["course"] == "BTI325"


def test_generate_study_plan_exam_type_passed_through():
    with patch("bb.tools.ai_tools.get_grades", return_value=[]), \
         patch("bb.tools.ai_tools.get_upcoming_deadlines", return_value=[]), \
         patch("bb.tools.ai_tools.list_downloaded_files", return_value=[]), \
         patch("bb.tools.ai_tools.get_course_content", return_value={}):
        result = generate_study_plan(course="BTI325", exam_type="midterm")
    assert result["exam_type"] == "midterm"


def test_generate_study_plan_graceful_empty(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        result = generate_study_plan(course="BTI325")
    assert result["grades"] == []
    assert result["upcoming_deadlines"] == []
    assert result["available_files"] == []
    assert result["content_tree"] == {}


def test_generate_study_plan_partial_failure():
    with patch("bb.tools.ai_tools.get_grades", side_effect=RuntimeError("db error")), \
         patch("bb.tools.ai_tools.get_upcoming_deadlines", return_value=MOCK_DEADLINES), \
         patch("bb.tools.ai_tools.list_downloaded_files", return_value=[]), \
         patch("bb.tools.ai_tools.get_course_content", return_value={}):
        result = generate_study_plan(course="BTI325")
    assert result["grades"] == []
    assert result["upcoming_deadlines"] == MOCK_DEADLINES


# ---------------------------------------------------------------------------
# extract_key_concepts
# ---------------------------------------------------------------------------

def test_extract_key_concepts_has_required_keys():
    with patch("bb.tools.ai_tools.list_downloaded_files", return_value=[]), \
         patch("bb.tools.ai_tools.get_course_content", return_value={}), \
         patch("bb.tools.ai_tools.search_content", return_value=[]):
        result = extract_key_concepts(course="BTI325")
    for key in ("course", "downloaded_files", "content_items"):
        assert key in result


def test_extract_key_concepts_flattens_nested_tree():
    with patch("bb.tools.ai_tools.list_downloaded_files", return_value=[]), \
         patch("bb.tools.ai_tools.get_course_content", return_value=MOCK_CONTENT_TREE), \
         patch("bb.tools.ai_tools.search_content", return_value=[]):
        result = extract_key_concepts(course="BTI325")
    titles = [i["title"] for i in result["content_items"]]
    assert "Lecture 1" in titles
    assert "Module 1" in titles
    assert "Quiz 1" in titles  # nested child must be included


def test_extract_key_concepts_content_items_shape():
    with patch("bb.tools.ai_tools.list_downloaded_files", return_value=[]), \
         patch("bb.tools.ai_tools.get_course_content", return_value=MOCK_CONTENT_TREE), \
         patch("bb.tools.ai_tools.search_content", return_value=[]):
        result = extract_key_concepts(course="BTI325")
    for item in result["content_items"]:
        assert "title" in item
        assert "type" in item
        assert "url" in item


def test_extract_key_concepts_deduplicates():
    search_hit = {"course": "BTI325", "title": "Lecture 1", "type": "file", "url": "https://bb.example.com/l1"}
    with patch("bb.tools.ai_tools.list_downloaded_files", return_value=[]), \
         patch("bb.tools.ai_tools.get_course_content", return_value=MOCK_CONTENT_TREE), \
         patch("bb.tools.ai_tools.search_content", return_value=[search_hit]):
        result = extract_key_concepts(course="BTI325")
    lecture_items = [i for i in result["content_items"] if i["title"] == "Lecture 1"]
    assert len(lecture_items) == 1


def test_extract_key_concepts_graceful_empty(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        result = extract_key_concepts(course="BTI325")
    assert result["downloaded_files"] == []
    assert result["content_items"] == []


def test_extract_key_concepts_graceful_when_queries_raise():
    with patch("bb.tools.ai_tools.list_downloaded_files", side_effect=RuntimeError), \
         patch("bb.tools.ai_tools.get_course_content", side_effect=RuntimeError), \
         patch("bb.tools.ai_tools.search_content", side_effect=RuntimeError):
        result = extract_key_concepts(course="BTI325")
    assert result["content_items"] == []


# ---------------------------------------------------------------------------
# estimate_study_time
# ---------------------------------------------------------------------------

def test_estimate_study_time_has_required_keys():
    with patch("bb.tools.ai_tools.get_grades", return_value=[]), \
         patch("bb.tools.ai_tools.get_upcoming_deadlines", return_value=[]), \
         patch("bb.tools.ai_tools.list_downloaded_files", return_value=[]):
        result = estimate_study_time(course="BTI325")
    for key in ("course", "target_grade", "current_grades", "remaining_deadlines", "downloaded_files"):
        assert key in result


def test_estimate_study_time_course_uppercased():
    with patch("bb.tools.ai_tools.get_grades", return_value=[]), \
         patch("bb.tools.ai_tools.get_upcoming_deadlines", return_value=[]), \
         patch("bb.tools.ai_tools.list_downloaded_files", return_value=[]):
        result = estimate_study_time(course="bti325")
    assert result["course"] == "BTI325"


def test_estimate_study_time_target_grade_passed_through():
    with patch("bb.tools.ai_tools.get_grades", return_value=[]), \
         patch("bb.tools.ai_tools.get_upcoming_deadlines", return_value=[]), \
         patch("bb.tools.ai_tools.list_downloaded_files", return_value=[]):
        result = estimate_study_time(course="BTI325", target_grade="A")
    assert result["target_grade"] == "A"


def test_estimate_study_time_graceful_empty(tmp_path):
    with patch("bb.config.BB_DIR", tmp_path):
        result = estimate_study_time(course="BTI325")
    assert result["current_grades"] == []
    assert result["remaining_deadlines"] == []
    assert result["downloaded_files"] == []


def test_estimate_study_time_partial_failure():
    with patch("bb.tools.ai_tools.get_grades", side_effect=RuntimeError), \
         patch("bb.tools.ai_tools.get_upcoming_deadlines", return_value=MOCK_DEADLINES), \
         patch("bb.tools.ai_tools.list_downloaded_files", return_value=[]):
        result = estimate_study_time(course="BTI325")
    assert result["current_grades"] == []
    assert result["remaining_deadlines"] == MOCK_DEADLINES


# ---------------------------------------------------------------------------
# TOOL_REGISTRY integration
# ---------------------------------------------------------------------------

def test_all_four_ai_tools_in_registry():
    from bb.tools import TOOL_REGISTRY
    for name in ("summarize_content", "generate_study_plan", "extract_key_concepts", "estimate_study_time"):
        assert name in TOOL_REGISTRY


def test_registry_entries_callable():
    from bb.tools import TOOL_REGISTRY
    for name, fn in TOOL_REGISTRY.items():
        assert callable(fn), f"{name} must be callable"
