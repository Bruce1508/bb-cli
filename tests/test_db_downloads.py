"""
Tests for bb/db.py — downloads table: record_download, get_downloads, MIGRATION_5

Strategy:
- Real SQLite (tmp_path) — no mocks
- Verify migration creates table, upsert logic, case normalization, filter
"""
from bb.db import Database


def test_migration_creates_downloads_table(tmp_path):
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        tables = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    assert any(t[0] == "downloads" for t in tables)


def test_record_download_inserts_row(tmp_path):
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        db.record_download("BTP200", "syllabus.pdf", "/tmp/syllabus.pdf", 1024)
        rows = db._conn.execute("SELECT * FROM downloads").fetchall()
    assert len(rows) == 1


def test_record_download_normalizes_course_to_upper(tmp_path):
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        db.record_download("btp200", "syllabus.pdf", "/tmp/syllabus.pdf", 1024)
        row = db._conn.execute("SELECT course FROM downloads").fetchone()
    assert row[0] == "BTP200"


def test_record_download_replaces_on_conflict(tmp_path):
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        db.record_download("BTP200", "syllabus.pdf", "/old/path.pdf", 100)
        db.record_download("BTP200", "syllabus.pdf", "/new/path.pdf", 200)
        rows = db._conn.execute("SELECT path, size_bytes FROM downloads").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "/new/path.pdf"
    assert rows[0][1] == 200


def test_get_downloads_returns_all(tmp_path):
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        db.record_download("BTP200", "a.pdf", "/a", 100)
        db.record_download("BTI325", "b.pdf", "/b", 200)
        result = db.get_downloads()
    assert len(result) == 2


def test_get_downloads_returns_empty_when_none(tmp_path):
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        result = db.get_downloads()
    assert result == []


def test_get_downloads_filters_by_course(tmp_path):
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        db.record_download("BTP200", "a.pdf", "/a", 100)
        db.record_download("BTI325", "b.pdf", "/b", 200)
        result = db.get_downloads(course="BTP200")
    assert len(result) == 1
    assert result[0]["course"] == "BTP200"


def test_get_downloads_filter_is_case_insensitive(tmp_path):
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        db.record_download("BTP200", "a.pdf", "/a", 100)
        result = db.get_downloads(course="btp200")
    assert len(result) == 1


def test_get_downloads_returns_dict_with_required_keys(tmp_path):
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        db.record_download("BTP200", "a.pdf", "/a", 100)
        result = db.get_downloads()
    assert set(result[0].keys()) == {"course", "filename", "path", "size_bytes", "downloaded_at"}


def test_record_download_accepts_none_size(tmp_path):
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        db.record_download("BTP200", "nosize.pdf", "/tmp/nosize.pdf", None)
        row = db._conn.execute("SELECT size_bytes FROM downloads").fetchone()
    assert row[0] is None


def test_migration_7_adds_url_and_record_download_stores_it(tmp_path):
    with Database(tmp_path / "bb.db") as db:
        db.setup()
        db.record_download("BTP200", "a.pdf", "/a", 1, url="https://h/a.pdf")
        row = db._conn.execute("SELECT url FROM downloads").fetchone()
        version = db._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    assert row[0] == "https://h/a.pdf" and version >= 7


def _v6_db(path):
    from bb.db import MIGRATIONS
    db = Database(path)
    for v in range(1, 7):
        db._conn.executescript(MIGRATIONS[v])
    return db


def test_migration_7_recovers_from_partial_apply(tmp_path):
    path = tmp_path / "bb.db"
    db = _v6_db(path)
    db._conn.execute("ALTER TABLE downloads ADD COLUMN url TEXT")  # crash before version insert
    db._conn.commit()
    db.close()
    with Database(path) as db2:
        db2.setup()
        assert db2._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 7


def test_migration_7_double_setup_on_two_instances(tmp_path):
    path = tmp_path / "bb.db"
    _v6_db(path).close()
    a, b = Database(path), Database(path)
    a.setup()
    b._conn.execute("SELECT 1")  # b opened while still at v6
    b.setup()
    assert b._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 7
    a.close()
    b.close()
