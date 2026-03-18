from __future__ import annotations

import sqlite3
from pathlib import Path

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

MIGRATIONS: dict[int, str] = {
    1: MIGRATION_1,
    # Day 2: 2: MIGRATION_2 — announcements + grades tables
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
