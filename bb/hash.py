from __future__ import annotations

from hashlib import sha256


def content_hash(course: str, title: str, due_at: str = "") -> str:
    """Return a stable SHA-256 hex digest for use as a DB primary key.

    Hashing course + title + due_at provides cross-source dedup: the same
    deadline arriving from both iCal and the Activity Stream produces the
    same ID and is stored only once.
    """
    payload = f"{course}|{title}|{due_at}".encode()
    return sha256(payload).hexdigest()
