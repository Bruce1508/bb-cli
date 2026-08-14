"""Pure diff + humanization logic for the change digest feature.

DB-free by design so it can be unit-tested with plain fixtures. The DB layer
(bb/db.py) calls diff_* inside upsert; all three surfaces call humanize().
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from bb.adapters.base import Deadline, GradeItem


@dataclass
class Change:
    course: str
    item_type: str  # 'deadline' | 'grade'
    item_id: str
    title: str
    field: str  # 'due_at' | 'score' | 'status'
    change_type: str  # 'due_moved' | 'grade_posted' | 'grade_changed'
    old_value: str | None
    new_value: str | None
    detected_at: str
    id: int | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def diff_deadline(old_due_at: str, new: Deadline) -> list[Change]:
    """Return a due_moved Change if the deadline's due date changed, else []."""
    new_due = new.due_at.isoformat()
    if old_due_at == new_due:
        return []
    return [
        Change(
            course=new.course, item_type="deadline", item_id=new.id,
            title=new.title, field="due_at", change_type="due_moved",
            old_value=old_due_at, new_value=new_due, detected_at=_now(),
        )
    ]


def diff_grade(old_score: float | None, old_status: str, new: GradeItem) -> list[Change]:
    """Return grade_posted / grade_changed Changes, or [] if nothing changed."""
    became_graded = new.status == "graded" and old_status != "graded"
    got_score = old_score is None and new.score is not None
    if became_graded or got_score:
        return [
            Change(
                course=new.course, item_type="grade", item_id=new.id,
                title=new.item, field="status", change_type="grade_posted",
                old_value=old_status, new_value=new.status, detected_at=_now(),
            )
        ]
    if old_score is not None and new.score is not None and new.score != old_score:
        return [
            Change(
                course=new.course, item_type="grade", item_id=new.id,
                title=new.item, field="score", change_type="grade_changed",
                old_value=str(old_score), new_value=str(new.score), detected_at=_now(),
            )
        ]
    return []


def _fmt_due(iso: str | None) -> str:
    if not iso:
        return "?"
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%a %b %-d")
    except (ValueError, TypeError):
        return iso


def _fragment(ch: Change) -> str:
    if ch.change_type == "due_moved":
        return f"{ch.title} due date moved to {_fmt_due(ch.new_value)}"
    if ch.change_type == "grade_posted":
        return f"{ch.title} now graded"
    if ch.change_type == "grade_changed":
        return f"{ch.title} grade changed {ch.old_value}→{ch.new_value}"
    return f"{ch.title} changed"


def humanize(changes: list[Change]) -> str:
    """Group changes by course into one line, e.g.
    'OPS445: Quiz 3 now graded; BTP200: Lab 4 due date moved to Fri Aug 8'."""
    by_course: dict[str, list[Change]] = {}
    for ch in changes:
        by_course.setdefault(ch.course, []).append(ch)
    parts = [
        f"{course}: {', '.join(_fragment(ch) for ch in chs)}"
        for course, chs in by_course.items()
    ]
    return "; ".join(parts)
