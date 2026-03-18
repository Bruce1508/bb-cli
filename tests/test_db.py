"""
Tests for bb/db.py

Success criteria:
- Database(":memory:").setup() creates schema without error
- schema_version table contains exactly version 1 after setup
- setup() is idempotent: calling it twice leaves version at 1
- deadlines table exists with correct columns
- sync_log table exists
- WAL journal mode is applied (tested with a real file, not :memory:)
- Database works as a context manager (__enter__ / __exit__)
- Default path is resolved at call time so BB_DIR patching works
"""
import sqlite3

import pytest


# ---------------------------------------------------------------------------
# Basic setup
# ---------------------------------------------------------------------------


def test_setup_completes_without_error():
    """Database(":memory:").setup() does not raise."""
    from bb.db import Database

    db = Database(":memory:")
    db.setup()
    db.close()


def test_schema_version_is_1_after_setup():
    """schema_version table has exactly one row: version = 1."""
    from bb.db import Database

    db = Database(":memory:")
    db.setup()
    cursor = db._conn.execute("SELECT version FROM schema_version")
    rows = cursor.fetchall()
    db.close()

    assert len(rows) == 1
    assert rows[0][0] == 1


def test_setup_is_idempotent():
    """Calling setup() twice does not raise and version remains 1."""
    from bb.db import Database

    db = Database(":memory:")
    db.setup()
    db.setup()  # second call must not raise or duplicate the version row
    cursor = db._conn.execute("SELECT COUNT(*) FROM schema_version")
    count = cursor.fetchone()[0]
    cursor2 = db._conn.execute("SELECT version FROM schema_version")
    version = cursor2.fetchone()[0]
    db.close()

    assert count == 1
    assert version == 1


# ---------------------------------------------------------------------------
# Table structure
# ---------------------------------------------------------------------------


def test_deadlines_table_exists_after_setup():
    """Migration 1 creates the 'deadlines' table."""
    from bb.db import Database

    db = Database(":memory:")
    db.setup()
    cursor = db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='deadlines'"
    )
    result = cursor.fetchone()
    db.close()

    assert result is not None


def test_deadlines_table_has_required_columns():
    """'deadlines' table has: id, course, title, due_at, source, created_at."""
    from bb.db import Database

    db = Database(":memory:")
    db.setup()
    cursor = db._conn.execute("PRAGMA table_info(deadlines)")
    columns = {row[1] for row in cursor.fetchall()}
    db.close()

    assert {"id", "course", "title", "due_at", "source", "created_at"}.issubset(columns)


def test_sync_log_table_exists_after_setup():
    """Migration 1 creates the 'sync_log' table."""
    from bb.db import Database

    db = Database(":memory:")
    db.setup()
    cursor = db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sync_log'"
    )
    result = cursor.fetchone()
    db.close()

    assert result is not None


def test_sync_log_table_has_required_columns():
    """'sync_log' table has: id, synced_at, source, items_new, items_updated, error."""
    from bb.db import Database

    db = Database(":memory:")
    db.setup()
    cursor = db._conn.execute("PRAGMA table_info(sync_log)")
    columns = {row[1] for row in cursor.fetchall()}
    db.close()

    assert {"id", "synced_at", "source", "items_new", "items_updated", "error"}.issubset(
        columns
    )


# ---------------------------------------------------------------------------
# WAL mode — must use a real file, not :memory:
# ---------------------------------------------------------------------------


def test_wal_journal_mode_is_applied(tmp_path):
    """PRAGMA journal_mode returns 'wal' after Database.setup() on a real file."""
    from bb.db import Database

    db_path = tmp_path / "test.db"
    db = Database(db_path)
    db.setup()
    cursor = db._conn.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    db.close()

    assert mode == "wal"


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


def test_database_works_as_context_manager():
    """Database supports 'with' statement; connection is closed on exit."""
    from bb.db import Database

    with Database(":memory:") as db:
        db.setup()
        cursor = db._conn.execute("SELECT version FROM schema_version")
        version = cursor.fetchone()[0]

    assert version == 1


def test_database_context_manager_closes_connection_on_exit():
    """After 'with' block exits, the connection is closed."""
    from bb.db import Database

    with Database(":memory:") as db:
        db.setup()

    # A closed sqlite3 connection raises ProgrammingError on any operation
    with pytest.raises(Exception):
        db._conn.execute("SELECT 1")


# ---------------------------------------------------------------------------
# BB_DIR patching (default path resolved at call time)
# ---------------------------------------------------------------------------


def test_default_path_uses_bb_dir_at_call_time(tmp_path):
    """When no path is given, Database uses BB_DIR resolved at instantiation time."""
    from unittest.mock import patch

    with patch("bb.db.BB_DIR", tmp_path):
        from bb.db import Database

        db = Database()  # should use patched BB_DIR / "bb.db"
        db.setup()
        db.close()

    assert (tmp_path / "bb.db").exists()
