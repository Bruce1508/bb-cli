from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Deadline:
    id: str
    course: str
    title: str
    due_at: datetime
    source: str  # 'ical' | 'stream'


@dataclass
class Announcement:
    id: str
    course: str
    title: str
    body: str
    posted_at: datetime
    read_at: datetime | None


@dataclass
class GradeItem:
    id: str
    course: str
    item: str
    score: float | None
    out_of: float | None
    status: str


class LMSAdapter(ABC):
    @abstractmethod
    def authenticate(self) -> None: ...

    @abstractmethod
    def check_session(self) -> str: ...

    # Returns: 'fresh' | 'uncertain' | 'expired'

    @abstractmethod
    def fetch_activity_stream(self) -> list[Deadline | Announcement | GradeItem]: ...

    @abstractmethod
    def fetch_grades(self) -> list[GradeItem]: ...

    @abstractmethod
    def fetch_course_content(self, course_id: str) -> object: ...
