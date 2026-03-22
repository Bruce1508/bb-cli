from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bb.adapters.base import Announcement, Deadline, GradeItem

BB_DIR = Path.home() / ".bb"

MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS deadlines (
    id TEXT PRIMARY KEY,
    course TEXT NOT NULL,
    title TEXT NOT NULL,
    due_at TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    notified_at TEXT
);
CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synced_at TEXT NOT NULL,
    source TEXT NOT NULL,
    items_new INTEGER DEFAULT 0,
    items_updated INTEGER DEFAULT 0,
    error TEXT
);
INSERT OR IGNORE INTO schema_version VALUES (1);
"""

MIGRATION_2 = """
CREATE TABLE IF NOT EXISTS announcements (
    id TEXT PRIMARY KEY,
    course TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    posted_at TEXT NOT NULL,
    read_at TEXT
);
CREATE TABLE IF NOT EXISTS grades (
    id TEXT PRIMARY KEY,
    course TEXT NOT NULL,
    item TEXT NOT NULL,
    score REAL,
    out_of REAL,
    status TEXT NOT NULL,
    notified_at TEXT
);
INSERT OR IGNORE INTO schema_version VALUES (2);
"""

MIGRATION_3 = """
CREATE TABLE IF NOT EXISTS notification_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    type     TEXT NOT NULL,
    sent_at  TEXT NOT NULL
);
INSERT OR IGNORE INTO schema_version VALUES (3);
"""

MIGRATION_4 = """
CREATE TABLE IF NOT EXISTS course_map (
    course_code  TEXT PRIMARY KEY,
    bb_id        TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
INSERT OR IGNORE INTO schema_version VALUES (4);
"""

MIGRATION_5 = """
CREATE TABLE IF NOT EXISTS downloads (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    course       TEXT NOT NULL,
    filename     TEXT NOT NULL,
    path         TEXT NOT NULL,
    size_bytes   INTEGER,
    downloaded_at TEXT NOT NULL,
    UNIQUE(course, filename)
);
INSERT OR IGNORE INTO schema_version VALUES (5);
"""

MIGRATIONS: dict[int, str] = {
    1: MIGRATION_1,
    2: MIGRATION_2,
    3: MIGRATION_3,
    4: MIGRATION_4,
    5: MIGRATION_5,
}


class Database:
    def __init__(self, path: str | Path | None = None) -> None:
        # Resolve BB_DIR at call time (not import time) so tests can patch bb.db.BB_DIR
        resolved = Path(path).expanduser() if path else BB_DIR / "bb.db"
        self._path = resolved
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute("PRAGMA journal_mode=WAL")

    def setup(self) -> None:
        """Run all pending migrations using executescript() for multi-statement SQL."""
        try:
            row = self._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
            current = row[0] if row[0] is not None else 0
        except sqlite3.OperationalError:
            current = 0

        for version in sorted(MIGRATIONS):
            if version > current:
                self._conn.executescript(MIGRATIONS[version])

    def close(self) -> None:
        """Close the SQLite connection."""
        self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Deadline CRUD
    # ------------------------------------------------------------------

    def upsert_deadline(self, d: Deadline) -> bool:
        """Insert or update a deadline. Returns True if the record is new."""
        due_str = d.due_at.isoformat()
        created_str = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO deadlines (id, course, title, due_at, source, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (d.id, d.course, d.title, due_str, d.source, created_str),
        )
        is_new = cur.rowcount > 0
        if not is_new:
            self._conn.execute(
                "UPDATE deadlines SET title=?, due_at=?, source=? WHERE id=?",
                (d.title, due_str, d.source, d.id),
            )
        self._conn.commit()
        return is_new

    # ------------------------------------------------------------------
    # Announcement CRUD
    # ------------------------------------------------------------------

    def upsert_announcement(self, a: Announcement) -> bool:
        """Insert or update an announcement. Returns True if the record is new."""
        posted_str = a.posted_at.isoformat()
        read_str = a.read_at.isoformat() if a.read_at else None
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO announcements (id, course, title, body, posted_at, read_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (a.id, a.course, a.title, a.body, posted_str, read_str),
        )
        is_new = cur.rowcount > 0
        if not is_new:
            self._conn.execute(
                "UPDATE announcements SET title=?, body=?, posted_at=? WHERE id=?",
                (a.title, a.body, posted_str, a.id),
            )
        self._conn.commit()
        return is_new

    # ------------------------------------------------------------------
    # Grade CRUD
    # ------------------------------------------------------------------

    def upsert_grade(self, g: GradeItem) -> bool:
        """Insert or update a grade item. Returns True if the record is new."""
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO grades (id, course, item, score, out_of, status)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (g.id, g.course, g.item, g.score, g.out_of, g.status),
        )
        is_new = cur.rowcount > 0
        if not is_new:
            self._conn.execute(
                "UPDATE grades SET item=?, score=?, out_of=?, status=? WHERE id=?",
                (g.item, g.score, g.out_of, g.status, g.id),
            )
        self._conn.commit()
        return is_new

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_upcoming_deadlines(
        self, days: int = 7, include_overdue: bool = False
    ) -> list[Deadline]:
        """Return deadlines within the next `days` days, sorted by due_at ascending."""
        now = datetime.now(timezone.utc)
        lower = (now - timedelta(days=1)) if include_overdue else now
        upper = now + timedelta(days=days)
        rows = self._conn.execute(
            "SELECT id, course, title, due_at, source FROM deadlines"
            " WHERE due_at >= ? AND due_at <= ? ORDER BY due_at ASC",
            (lower.isoformat(), upper.isoformat()),
        ).fetchall()
        return [
            Deadline(
                id=r[0],
                course=r[1],
                title=r[2],
                due_at=datetime.fromisoformat(r[3]),
                source=r[4],
            )
            for r in rows
        ]

    def get_recent_announcements(self, limit: int = 20) -> list[Announcement]:
        """Return the most recent announcements, newest first."""
        rows = self._conn.execute(
            "SELECT id, course, title, body, posted_at, read_at FROM announcements"
            " ORDER BY posted_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            Announcement(
                id=r[0],
                course=r[1],
                title=r[2],
                body=r[3],
                posted_at=datetime.fromisoformat(r[4]),
                read_at=datetime.fromisoformat(r[5]) if r[5] else None,
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Sync log
    # ------------------------------------------------------------------

    def log_sync(
        self,
        source: str,
        items_new: int,
        items_updated: int,
        error: str | None = None,
    ) -> None:
        """Record a sync event in sync_log."""
        self._conn.execute(
            "INSERT INTO sync_log (synced_at, source, items_new, items_updated, error)"
            " VALUES (?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), source, items_new, items_updated, error),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Notification cooldown
    # ------------------------------------------------------------------

    def was_notified_recently(self, ntype: str, within_hours: int = 24) -> bool:
        """Return True if a notification of this type was sent within N hours."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=within_hours)).isoformat()
        try:
            row = self._conn.execute(
                "SELECT 1 FROM notification_log WHERE type=? AND sent_at >= ? LIMIT 1",
                (ntype, cutoff),
            ).fetchone()
        except sqlite3.OperationalError:
            return False
        return row is not None

    def log_notification(self, ntype: str) -> None:
        """Record that a notification of this type was sent now."""
        self._conn.execute(
            "INSERT INTO notification_log (type, sent_at) VALUES (?, ?)",
            (ntype, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Course map
    # ------------------------------------------------------------------

    def upsert_course_map(
        self,
        course_code: str,
        bb_id: str,
        display_name: str = "",
    ) -> None:
        """Save or update course_code → bb_id mapping."""
        self._conn.execute(
            """INSERT INTO course_map (course_code, bb_id, display_name, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(course_code) DO UPDATE SET
                   bb_id=excluded.bb_id,
                   display_name=excluded.display_name,
                   updated_at=excluded.updated_at""",
            (course_code.upper(), bb_id, display_name, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def get_course_bb_id(self, course_code: str) -> str | None:
        """Return Blackboard internal ID for a course code, or None if not found."""
        row = self._conn.execute(
            "SELECT bb_id FROM course_map WHERE course_code = ?",
            (course_code.upper(),),
        ).fetchone()
        return row[0] if row else None

    # ------------------------------------------------------------------
    # Downloads
    # ------------------------------------------------------------------

    def record_download(
        self,
        course: str,
        filename: str,
        path: str,
        size_bytes: int | None,
    ) -> None:
        """Upsert download record. course stored as UPPER(course).

        Preserves row id on re-download.
        """
        self._conn.execute(
            "INSERT INTO downloads (course, filename, path, size_bytes, downloaded_at)"
            " VALUES (UPPER(?), ?, ?, ?, ?)"
            " ON CONFLICT(course, filename) DO UPDATE SET"
            "   path=excluded.path,"
            "   size_bytes=excluded.size_bytes,"
            "   downloaded_at=excluded.downloaded_at",
            (course, filename, path, size_bytes, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def get_downloads(self, course: str | None = None) -> list[dict]:
        """Return downloads, optionally filtered by course (case-insensitive)."""
        if course:
            rows = self._conn.execute(
                "SELECT course, filename, path, size_bytes, downloaded_at"
                " FROM downloads WHERE UPPER(course) = UPPER(?)"
                " ORDER BY downloaded_at DESC",
                (course,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT course, filename, path, size_bytes, downloaded_at"
                " FROM downloads ORDER BY downloaded_at DESC"
            ).fetchall()
        return [
            {
                "course": r[0],
                "filename": r[1],
                "path": r[2],
                "size_bytes": r[3],
                "downloaded_at": r[4],
            }
            for r in rows
        ]
