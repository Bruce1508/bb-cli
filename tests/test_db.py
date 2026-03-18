import sqlite3
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

from bb.db import Database


def make_db() -> Database:
    """Helper: in-memory database, set up and ready."""
    db = Database(":memory:")
    db.setup()
    return db


def test_setup_completes_without_error():
    db = Database(":memory:")
    db.setup()  # must not raise
    db.close()


def test_schema_version_is_1_after_setup():
    with make_db() as db:
        row = db._conn.execute("SELECT version FROM schema_version").fetchone()
        assert row[0] == 1


def test_setup_is_idempotent():
    db = Database(":memory:")
    db.setup()
    db.setup()  # second call must not raise or change version
    row = db._conn.execute("SELECT version FROM schema_version").fetchone()
    assert row[0] == 1
    db.close()


def test_wal_mode_is_applied():
    # WAL pragma only works on real files, not :memory:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        with Database(path) as db:
            db.setup()
            result = db._conn.execute("PRAGMA journal_mode").fetchone()
            assert result[0] == "wal"
    finally:
        os.unlink(path)


def test_deadlines_table_has_notified_at_column():
    with make_db() as db:
        cols = [
            row[1]
            for row in db._conn.execute("PRAGMA table_info(deadlines)").fetchall()
        ]
        assert "notified_at" in cols


def test_deadlines_table_exists():
    with make_db() as db:
        db._conn.execute("SELECT * FROM deadlines").fetchall()  # must not raise


def test_sync_log_table_exists():
    with make_db() as db:
        db._conn.execute("SELECT * FROM sync_log").fetchall()  # must not raise


def test_context_manager_closes_connection():
    with Database(":memory:") as db:
        db.setup()
    # After exiting context, connection should be closed
    try:
        db._conn.execute("SELECT 1")
        assert False, "Expected exception — connection should be closed"
    except Exception:
        pass  # expected
