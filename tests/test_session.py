"""
Tests for bb/security/session.py

Strategy:
- Use tmp_path for isolated session file paths
- Patch _get_key_from_keyring to return a fixed Fernet key (bypasses OS keyring)
- Mock time.time() to test age threshold boundaries without sleeping

Success criteria:
- SessionError is a subclass of Exception
- encrypt_session writes a binary (non-plaintext) file with 0o600 permissions
- decrypt_session raises SessionError on missing or corrupt file
- encrypt → decrypt roundtrip recovers original dict (including nested structures)
- delete_session removes the file; no-op when file is missing
- check_session_age: expired (missing), fresh (<6h), uncertain (6–24h), expired (≥24h)
- Boundary values at FRESH_THRESHOLD and UNCERTAIN_THRESHOLD are correct
- session_exists: True/False based on file presence
- _derive_key_from_password: deterministic, produces valid Fernet key, collision-resistant
- get_key uses stored keyring key when available; generates + stores new key on first run
"""
import time
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from bb.security.session import (
    FRESH_THRESHOLD,
    UNCERTAIN_THRESHOLD,
    SessionError,
    SessionManager,
)

# Fixed Fernet key shared across all tests that need encryption
TEST_KEY: bytes = Fernet.generate_key()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sm(tmp_path):
    """SessionManager with an isolated path and a deterministic key (no real keyring)."""
    mgr = SessionManager(tmp_path / "session.enc")
    with patch.object(mgr, "_get_key_from_keyring", return_value=TEST_KEY):
        yield mgr


# ---------------------------------------------------------------------------
# Exception type
# ---------------------------------------------------------------------------


def test_session_error_is_subclass_of_exception():
    assert issubclass(SessionError, Exception)


# ---------------------------------------------------------------------------
# session_exists
# ---------------------------------------------------------------------------


def test_session_exists_false_when_no_file(tmp_path):
    mgr = SessionManager(tmp_path / "session.enc")
    assert mgr.session_exists() is False


def test_session_exists_true_after_encrypt(sm, tmp_path):
    sm.encrypt_session({"cookies": []})
    assert sm.session_exists() is True


# ---------------------------------------------------------------------------
# encrypt_session
# ---------------------------------------------------------------------------


def test_encrypt_creates_file(sm, tmp_path):
    sm.encrypt_session({"cookies": []})
    assert (tmp_path / "session.enc").exists()


def test_encrypt_file_is_binary_not_plaintext(sm, tmp_path):
    sm.encrypt_session({"cookies": [{"name": "secret_token", "value": "abc123"}]})
    content = (tmp_path / "session.enc").read_bytes()
    assert b"secret_token" not in content
    assert b"abc123" not in content


def test_encrypt_sets_600_permissions(sm, tmp_path):
    sm.encrypt_session({"cookies": []})
    mode = (tmp_path / "session.enc").stat().st_mode & 0o777
    assert mode == 0o600


# ---------------------------------------------------------------------------
# decrypt_session
# ---------------------------------------------------------------------------


def test_decrypt_raises_session_error_when_missing(tmp_path):
    mgr = SessionManager(tmp_path / "session.enc")
    with patch.object(mgr, "_get_key_from_keyring", return_value=TEST_KEY):
        with pytest.raises(SessionError):
            mgr.decrypt_session()


def test_decrypt_raises_session_error_on_corrupt_file(sm, tmp_path):
    (tmp_path / "session.enc").write_bytes(b"this-is-not-valid-fernet-ciphertext")
    with pytest.raises(SessionError):
        sm.decrypt_session()


def test_decrypt_restores_original_flat_dict(sm):
    original = {"cookies": [{"name": "session_id", "value": "xyz"}]}
    sm.encrypt_session(original)
    assert sm.decrypt_session() == original


def test_decrypt_restores_nested_dict(sm):
    original = {
        "cookies": [{"name": "tok", "value": "abc", "domain": ".example.com"}],
        "origins": [{"origin": "https://example.com", "localStorage": []}],
    }
    sm.encrypt_session(original)
    assert sm.decrypt_session() == original


def test_decrypt_restores_empty_dict(sm):
    sm.encrypt_session({})
    assert sm.decrypt_session() == {}


# ---------------------------------------------------------------------------
# delete_session
# ---------------------------------------------------------------------------


def test_delete_session_removes_file(sm, tmp_path):
    sm.encrypt_session({"cookies": []})
    sm.delete_session()
    assert not (tmp_path / "session.enc").exists()


def test_delete_session_is_noop_when_file_missing(tmp_path):
    mgr = SessionManager(tmp_path / "session.enc")
    mgr.delete_session()  # must not raise


# ---------------------------------------------------------------------------
# check_session_age — missing file
# ---------------------------------------------------------------------------


def test_check_session_age_expired_when_no_file(tmp_path):
    mgr = SessionManager(tmp_path / "session.enc")
    assert mgr.check_session_age() == "expired"


# ---------------------------------------------------------------------------
# check_session_age — with file present, mocked time
# ---------------------------------------------------------------------------


def test_check_session_age_fresh_at_1_minute(sm, tmp_path):
    sm.encrypt_session({"cookies": []})
    mtime = (tmp_path / "session.enc").stat().st_mtime
    with patch("time.time", return_value=mtime + 60):  # 1 minute after
        assert sm.check_session_age() == "fresh"


def test_check_session_age_fresh_just_below_threshold(sm, tmp_path):
    """1 second before the 6h fresh boundary → still fresh."""
    sm.encrypt_session({"cookies": []})
    mtime = (tmp_path / "session.enc").stat().st_mtime
    with patch("time.time", return_value=mtime + FRESH_THRESHOLD - 1):
        assert sm.check_session_age() == "fresh"


def test_check_session_age_uncertain_just_above_fresh_threshold(sm, tmp_path):
    """1 second past the 6h fresh boundary → uncertain."""
    sm.encrypt_session({"cookies": []})
    mtime = (tmp_path / "session.enc").stat().st_mtime
    with patch("time.time", return_value=mtime + FRESH_THRESHOLD + 1):
        assert sm.check_session_age() == "uncertain"


def test_check_session_age_uncertain_at_12h(sm, tmp_path):
    sm.encrypt_session({"cookies": []})
    mtime = (tmp_path / "session.enc").stat().st_mtime
    with patch("time.time", return_value=mtime + 12 * 3600):
        assert sm.check_session_age() == "uncertain"


def test_check_session_age_uncertain_just_below_expired_threshold(sm, tmp_path):
    """1 second before the 24h expiry boundary → uncertain."""
    sm.encrypt_session({"cookies": []})
    mtime = (tmp_path / "session.enc").stat().st_mtime
    with patch("time.time", return_value=mtime + UNCERTAIN_THRESHOLD - 1):
        assert sm.check_session_age() == "uncertain"


def test_check_session_age_expired_just_above_uncertain_threshold(sm, tmp_path):
    """1 second past the 24h boundary → expired."""
    sm.encrypt_session({"cookies": []})
    mtime = (tmp_path / "session.enc").stat().st_mtime
    with patch("time.time", return_value=mtime + UNCERTAIN_THRESHOLD + 1):
        assert sm.check_session_age() == "expired"


def test_check_session_age_expired_at_25h(sm, tmp_path):
    sm.encrypt_session({"cookies": []})
    mtime = (tmp_path / "session.enc").stat().st_mtime
    with patch("time.time", return_value=mtime + 25 * 3600):
        assert sm.check_session_age() == "expired"


# ---------------------------------------------------------------------------
# _derive_key_from_password
# ---------------------------------------------------------------------------


def test_derive_key_returns_bytes(tmp_path):
    mgr = SessionManager(tmp_path / "session.enc")
    key = mgr._derive_key_from_password("test-password")
    assert isinstance(key, bytes)


def test_derive_key_produces_valid_fernet_key(tmp_path):
    mgr = SessionManager(tmp_path / "session.enc")
    key = mgr._derive_key_from_password("test-password")
    Fernet(key)  # raises ValueError if the key is invalid


def test_derive_key_is_deterministic(tmp_path):
    mgr = SessionManager(tmp_path / "session.enc")
    key1 = mgr._derive_key_from_password("same-password")
    key2 = mgr._derive_key_from_password("same-password")
    assert key1 == key2


def test_derive_key_different_passwords_produce_different_keys(tmp_path):
    mgr = SessionManager(tmp_path / "session.enc")
    key_a = mgr._derive_key_from_password("password-A")
    key_b = mgr._derive_key_from_password("password-B")
    assert key_a != key_b


def test_derive_key_encrypt_decrypt_roundtrip(tmp_path):
    """Keys derived from the same password should encrypt/decrypt correctly."""
    mgr = SessionManager(tmp_path / "session.enc")
    key = mgr._derive_key_from_password("roundtrip-password")
    original = {"cookies": [{"name": "tok", "value": "xyz"}]}

    with patch.object(mgr, "_get_key_from_keyring", return_value=key):
        mgr.encrypt_session(original)
        recovered = mgr.decrypt_session()
    assert recovered == original


# ---------------------------------------------------------------------------
# get_key — keyring integration
# ---------------------------------------------------------------------------


def test_get_key_returns_stored_key_from_keyring(tmp_path):
    """When keyring has a stored key, get_key returns it."""
    mgr = SessionManager(tmp_path / "session.enc")
    stored_key = Fernet.generate_key().decode()
    with patch("keyring.get_password", return_value=stored_key):
        key = mgr.get_key()
    assert key == stored_key.encode()


def test_get_key_generates_and_stores_new_key_on_first_run(tmp_path):
    """When keyring returns None (first run), a new key is generated and stored."""
    mgr = SessionManager(tmp_path / "session.enc")
    with (
        patch("keyring.get_password", return_value=None),
        patch("keyring.set_password") as mock_set,
    ):
        key = mgr.get_key()
    assert isinstance(key, bytes)
    Fernet(key)  # valid Fernet key
    mock_set.assert_called_once()
