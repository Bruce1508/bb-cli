from __future__ import annotations

import base64
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import keyring
import keyring.errors
from cryptography.fernet import Fernet, InvalidToken

BB_DIR = Path.home() / ".bb"

# Age thresholds in seconds
FRESH_THRESHOLD: int = 6 * 3600  # < 6 h  → fresh
UNCERTAIN_THRESHOLD: int = 24 * 3600  # 6–24 h → uncertain
# ≥ 24 h → expired

KEYRING_SERVICE: str = "bb-cli"
KEYRING_USERNAME: str = "fernet-key"

# PBKDF2 fallback constants (OWASP 2023 recommendation)
_PBKDF2_SALT: bytes = b"bb-cli-static-salt-v1"
_PBKDF2_ITERATIONS: int = 600_000


class SessionError(Exception):
    """Raised when the session file is missing, corrupt, or decryption fails."""


class SessionManager:
    """Manages the encrypted Playwright session file at ~/.bb/session.enc."""

    def __init__(self, path: Path | None = None) -> None:
        # Resolve BB_DIR at call time (not import time) — tests patch bb.security.session.BB_DIR
        self._path: Path = path if path is not None else BB_DIR / "session.enc"

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def encrypt_session(self, storage_state: dict) -> None:
        """Serialize and encrypt a Playwright storage_state dict to disk."""
        plaintext = json.dumps(storage_state).encode()
        key = self.get_key()
        ciphertext = Fernet(key).encrypt(plaintext)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(ciphertext)
        self._path.chmod(0o600)  # owner-read-only, like SSH private keys

    def decrypt_session(self) -> dict:
        """Decrypt and return the storage_state dict from disk.

        Raises SessionError if the file is missing or decryption fails.
        """
        try:
            ciphertext = self._path.read_bytes()
        except FileNotFoundError:
            raise SessionError(f"No session file found at {self._path}. Run 'bb auth' first.")
        try:
            key = self.get_key()
            plaintext = Fernet(key).decrypt(ciphertext)
            return json.loads(plaintext)
        except InvalidToken as exc:
            raise SessionError("Session file is corrupt or the encryption key changed.") from exc

    def check_session_age(self) -> str:
        """Classify session by file mtime.

        Returns: 'fresh' | 'uncertain' | 'expired'
        Missing file is treated as 'expired'.
        """
        mtime = self._mtime()
        if mtime is None:
            return "expired"
        age_seconds = time.time() - mtime.timestamp()
        if age_seconds < FRESH_THRESHOLD:
            return "fresh"
        if age_seconds < UNCERTAIN_THRESHOLD:
            return "uncertain"
        return "expired"

    def session_exists(self) -> bool:
        """Return True if the encrypted session file exists."""
        return self._path.exists()

    def delete_session(self) -> None:
        """Remove the session file. No-op if it does not exist."""
        self._path.unlink(missing_ok=True)

    def get_key(self) -> bytes:
        """Return the Fernet key from keyring, or derive one via PBKDF2 fallback."""
        stored = self._get_key_from_keyring()
        if stored is not None:
            return stored
        # Keyring unavailable or empty — derive from user password
        import typer

        password = typer.prompt("Session password (used to encrypt your session)", hide_input=True)
        return self._derive_key_from_password(password)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_key_from_keyring(self) -> bytes | None:
        """Return the stored Fernet key bytes from OS keyring, or None."""
        try:
            stored = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
            if stored is None:
                # First run — generate and store a new key
                key = Fernet.generate_key()  # 44-byte URL-safe base64
                keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, key.decode())
                return key
            return stored.encode()
        except (keyring.errors.NoKeyringError, keyring.errors.KeyringError, Exception):
            return None

    def _derive_key_from_password(self, password: str) -> bytes:
        """PBKDF2-HMAC-SHA256: password → Fernet key (base64-encoded bytes)."""
        raw = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            _PBKDF2_SALT,
            _PBKDF2_ITERATIONS,
            dklen=32,
        )
        return base64.urlsafe_b64encode(raw)

    def _mtime(self) -> datetime | None:
        """Return session file mtime as UTC datetime, or None if file is absent."""
        try:
            ts = self._path.stat().st_mtime
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except FileNotFoundError:
            return None
