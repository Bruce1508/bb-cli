"""
Tests for bb/adapters/base.py

Success criteria:
- LMSAdapter cannot be instantiated directly (ABC)
- All 5 abstract methods are declared
- A concrete subclass missing any method raises TypeError
- Deadline, Announcement, GradeItem dataclasses have correct fields and types
"""
import pytest
from dataclasses import fields
from datetime import datetime, timezone

from bb.adapters.base import Announcement, Deadline, GradeItem, LMSAdapter


# ---------------------------------------------------------------------------
# LMSAdapter ABC contract
# ---------------------------------------------------------------------------


def test_lms_adapter_cannot_be_instantiated():
    with pytest.raises(TypeError):
        LMSAdapter()  # type: ignore[abstract]


def test_all_abstract_methods_declared():
    expected = {"authenticate", "check_session", "fetch_activity_stream", "fetch_grades", "fetch_course_content"}
    assert LMSAdapter.__abstractmethods__ == expected


def test_concrete_adapter_missing_one_method_raises_type_error():
    class IncompleteAdapter(LMSAdapter):
        def authenticate(self) -> None: ...
        def check_session(self) -> str: return "fresh"
        def fetch_activity_stream(self): return []
        def fetch_grades(self): return []
        # fetch_course_content intentionally omitted

    with pytest.raises(TypeError):
        IncompleteAdapter()


def test_concrete_adapter_with_all_methods_can_be_instantiated():
    class FullAdapter(LMSAdapter):
        def authenticate(self) -> None: ...
        def check_session(self) -> str: return "fresh"
        def fetch_activity_stream(self): return []
        def fetch_grades(self): return []
        def fetch_course_content(self, course_id: str): return {}

    adapter = FullAdapter()  # must not raise
    assert isinstance(adapter, LMSAdapter)


def test_check_session_returns_valid_status_string():
    class FullAdapter(LMSAdapter):
        def authenticate(self) -> None: ...
        def check_session(self) -> str: return "fresh"
        def fetch_activity_stream(self): return []
        def fetch_grades(self): return []
        def fetch_course_content(self, course_id: str): return {}

    adapter = FullAdapter()
    result = adapter.check_session()
    assert result in ("fresh", "uncertain", "expired")


# ---------------------------------------------------------------------------
# Deadline dataclass
# ---------------------------------------------------------------------------


def test_deadline_has_required_fields():
    field_names = {f.name for f in fields(Deadline)}
    assert {"id", "course", "title", "due_at", "source"}.issubset(field_names)


def test_deadline_can_be_constructed():
    now = datetime.now(timezone.utc)
    dl = Deadline(id="dl-1", course="BTP200", title="Lab 1", due_at=now, source="ical")
    assert dl.id == "dl-1"
    assert dl.course == "BTP200"
    assert dl.title == "Lab 1"
    assert dl.due_at == now
    assert dl.source == "ical"


def test_deadline_due_at_is_datetime():
    now = datetime.now(timezone.utc)
    dl = Deadline(id="dl-1", course="BTP200", title="Lab 1", due_at=now, source="ical")
    assert isinstance(dl.due_at, datetime)


# ---------------------------------------------------------------------------
# Announcement dataclass
# ---------------------------------------------------------------------------


def test_announcement_has_required_fields():
    field_names = {f.name for f in fields(Announcement)}
    assert {"id", "course", "title", "body", "posted_at", "read_at"}.issubset(field_names)


def test_announcement_read_at_can_be_none():
    now = datetime.now(timezone.utc)
    ann = Announcement(id="a-1", course="OOP244", title="Info", body="Body", posted_at=now, read_at=None)
    assert ann.read_at is None


def test_announcement_can_be_constructed():
    now = datetime.now(timezone.utc)
    ann = Announcement(id="a-1", course="OOP244", title="Info", body="Details", posted_at=now, read_at=None)
    assert ann.id == "a-1"
    assert ann.body == "Details"


# ---------------------------------------------------------------------------
# GradeItem dataclass
# ---------------------------------------------------------------------------


def test_grade_item_has_required_fields():
    field_names = {f.name for f in fields(GradeItem)}
    assert {"id", "course", "item", "score", "out_of", "status"}.issubset(field_names)


def test_grade_item_score_can_be_none():
    g = GradeItem(id="g-1", course="BTP200", item="Lab 1", score=None, out_of=20.0, status="pending")
    assert g.score is None


def test_grade_item_out_of_can_be_none():
    g = GradeItem(id="g-1", course="BTP200", item="Lab 1", score=18.0, out_of=None, status="graded")
    assert g.out_of is None


def test_grade_item_can_be_constructed():
    g = GradeItem(id="g-1", course="BTP200", item="Lab 1", score=18.0, out_of=20.0, status="graded")
    assert g.score == 18.0
    assert g.out_of == 20.0
    assert g.status == "graded"
