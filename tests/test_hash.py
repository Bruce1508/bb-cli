"""
Tests for bb/hash.py

Success criteria:
- content_hash() returns a non-empty hex string
- Same inputs always return the same hash (deterministic)
- Different inputs return different hashes
- Changing any one field produces a different hash
- Hash is safe to use as a DB primary key (string, no special chars)
"""
from bb.hash import content_hash


# ---------------------------------------------------------------------------
# Basic contract
# ---------------------------------------------------------------------------


def test_content_hash_returns_a_string():
    result = content_hash(course="BTP200", title="Lab 1", due_at="2026-03-25T23:59:00Z")
    assert isinstance(result, str)


def test_content_hash_is_non_empty():
    result = content_hash(course="BTP200", title="Lab 1", due_at="2026-03-25T23:59:00Z")
    assert len(result) > 0


def test_content_hash_is_hex_string():
    result = content_hash(course="BTP200", title="Lab 1", due_at="2026-03-25T23:59:00Z")
    int(result, 16)  # raises ValueError if not valid hex


def test_content_hash_is_safe_for_db_primary_key():
    result = content_hash(course="BTP200", title="Lab 1", due_at="2026-03-25T23:59:00Z")
    # No spaces, quotes, or special characters that would break SQL
    assert " " not in result
    assert "'" not in result
    assert '"' not in result


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_same_inputs_return_same_hash():
    h1 = content_hash(course="BTP200", title="Lab 1", due_at="2026-03-25T23:59:00Z")
    h2 = content_hash(course="BTP200", title="Lab 1", due_at="2026-03-25T23:59:00Z")
    assert h1 == h2


def test_hash_is_deterministic_across_multiple_calls():
    results = [
        content_hash(course="OOP244", title="Workshop 3", due_at="2026-04-01T11:59:00Z")
        for _ in range(5)
    ]
    assert len(set(results)) == 1  # all identical


# ---------------------------------------------------------------------------
# Collision resistance — different inputs → different hashes
# ---------------------------------------------------------------------------


def test_different_course_produces_different_hash():
    h1 = content_hash(course="BTP200", title="Lab 1", due_at="2026-03-25T23:59:00Z")
    h2 = content_hash(course="OOP244", title="Lab 1", due_at="2026-03-25T23:59:00Z")
    assert h1 != h2


def test_different_title_produces_different_hash():
    h1 = content_hash(course="BTP200", title="Lab 1", due_at="2026-03-25T23:59:00Z")
    h2 = content_hash(course="BTP200", title="Lab 2", due_at="2026-03-25T23:59:00Z")
    assert h1 != h2


def test_different_due_at_produces_different_hash():
    h1 = content_hash(course="BTP200", title="Lab 1", due_at="2026-03-25T23:59:00Z")
    h2 = content_hash(course="BTP200", title="Lab 1", due_at="2026-03-26T23:59:00Z")
    assert h1 != h2


def test_due_at_defaults_to_empty_string():
    # content_hash with no due_at should not raise
    result = content_hash(course="BTP200", title="Announcement")
    assert isinstance(result, str)
    assert len(result) > 0


def test_hash_without_due_at_differs_from_hash_with_due_at():
    h1 = content_hash(course="BTP200", title="Lab 1")
    h2 = content_hash(course="BTP200", title="Lab 1", due_at="2026-03-25T23:59:00Z")
    assert h1 != h2
