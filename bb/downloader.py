"""Download Blackboard files using authenticated session cookies.

Uses httpx with cookies extracted from the encrypted session file.
No Playwright required — cookies from storage_state JSON work for direct HTTP.
"""

from __future__ import annotations

import contextlib
import hashlib
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from bb.models.content import ContentItem
from bb.security.session import SessionError, SessionManager

if TYPE_CHECKING:
    from bb.db import Database

CHUNK_SIZE: int = 65536  # 64 KB read chunks for streaming downloads


class DownloadError(Exception):
    """Raised on HTTP error, timeout, or failed request. Callers catch and continue."""


class Downloader:
    """Stream Blackboard files to disk using session cookies."""

    def __init__(self, session_manager: SessionManager) -> None:
        self._sm = session_manager

    def _extract_cookies(self) -> httpx.Cookies:
        """Decrypt session → cookie jar scoped to each cookie's own domain and path.

        Scoping matters because downloads follow redirects: a plain dict would send the
        Blackboard session to whatever host (e.g. a CDN) the redirect points at.
        Raises: SessionError if session file missing or corrupt.
        """
        state = self._sm.decrypt_session()  # raises SessionError on failure
        jar = httpx.Cookies()
        for c in state.get("cookies", []):
            jar.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))
        return jar

    def download(self, url: str, dest_dir: Path, filename: str) -> Path:
        """Stream url to dest_dir/<filename> using session cookies.

        Handles filename conflicts via _resolve_filename.
        Returns: resolved path of saved file.
        Raises: DownloadError on HTTP 4xx/5xx or timeout.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = self._resolve_filename(dest_dir, filename)
        try:
            cookies = self._extract_cookies()
            with httpx.Client(
                cookies=cookies,
                timeout=httpx.Timeout(30.0, read=300.0),
                follow_redirects=True,
            ) as client:
                with client.stream("GET", url) as response:
                    response.raise_for_status()
                    with open(dest_path, "wb") as f:
                        for chunk in response.iter_bytes(chunk_size=CHUNK_SIZE):
                            f.write(chunk)
        except httpx.HTTPStatusError as e:
            dest_path.unlink(missing_ok=True)
            raise DownloadError(f"HTTP {e.response.status_code}") from e
        except httpx.TimeoutException as e:
            dest_path.unlink(missing_ok=True)
            raise DownloadError("Timeout") from e
        except httpx.RequestError as e:
            dest_path.unlink(missing_ok=True)
            raise DownloadError(str(e)) from e
        except OSError:  # disk full, permission, name too long: no partial file left behind
            with contextlib.suppress(OSError):
                dest_path.unlink(missing_ok=True)
            raise
        return dest_path

    def _resolve_filename(self, dest_dir: Path, filename: str) -> Path:
        """Return a non-conflicting path: file.pdf → file_1.pdf → file_2.pdf."""
        candidate = dest_dir / filename
        if not candidate.exists():
            return candidate
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        counter = 1
        while True:
            candidate = dest_dir / f"{stem}_{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1


def ext_from_url(url: str | None) -> str:
    """'https://host/file.pdf?x=1' → '.pdf'; '' when there is no extension."""
    if not url:
        return ""
    path_part = url.split("?")[0].split("/")[-1]
    return ("." + path_part.rsplit(".", 1)[-1]) if "." in path_part else ""


def collect_downloadable(items: list[ContentItem]) -> list[ContentItem]:
    """DFS: every ContentItem that has a download_url."""
    result: list[ContentItem] = []
    for item in items:
        if item.download_url:
            result.append(item)
        result.extend(collect_downloadable(item.children))
    return result


def safe_filename(item: ContentItem, unique: bool = False) -> str:
    """Filename for a downloaded item: never a path, never hidden, never empty.

    Titles come from Blackboard (untrusted), so path separators are replaced, control
    characters (NUL etc.) dropped, the stem capped at 150 chars, and a title made only of
    dots/spaces (e.g. "..") becomes "file". unique=True appends a hash of the download url
    ("Slides-1a2b3c.pdf") so same-titled items never share a file.
    """
    stem = _CONTROL.sub("", item.title).replace("/", "_").replace("\\", "_").strip()
    if not stem.strip(". "):
        stem = "file"
    stem = stem.lstrip(".")[:_STEM_MAX]
    if unique:
        stem += "-" + hashlib.sha1((item.download_url or "").encode()).hexdigest()[:6]
    return stem + _CONTROL.sub("", ext_from_url(item.download_url))


_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_STEM_MAX = 150


def already_downloaded(db: Database, course_code: str, url: str) -> str | None:
    """Filename of a recorded, non-empty download of this url, else None."""
    row = db.download_by_url(course_code, url)
    if row is None:
        return None
    path = Path(row[1])
    return row[0] if path.is_file() and path.stat().st_size > 0 else None


@dataclass
class DownloadReport:
    saved: list[Path] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def download_items(
    items: list[ContentItem],
    course_code: str,
    dest_dir: Path,
    downloader: Downloader,
    db: Database,
    on_event: Callable[[str, str, str], None] | None = None,
) -> DownloadReport:
    """Download each item unless this url was already downloaded; record successes in the DB.

    Same-titled items (e.g. "Lecture Slides" in every week) get a url-hash suffix so they
    never overwrite or stand in for each other. Failures are collected in the report, never
    raised, so one bad file can't stop the rest.
    """
    report = DownloadReport()
    emit = on_event or (lambda *_: None)
    name_counts = Counter(safe_filename(i) for i in items)
    for item in items:
        url = item.download_url
        filename = safe_filename(item)
        try:
            had = already_downloaded(db, course_code, url)
            if had:
                report.skipped.append(had)
                emit("skipped", had, "already downloaded")
                continue
            if name_counts[filename] > 1 or (
                (dest_dir / filename).exists()
                and db.download_url_for_file(course_code, filename) != url
            ):
                filename = safe_filename(item, unique=True)
            saved = downloader.download(url, dest_dir, filename)
            size = saved.stat().st_size
            db.record_download(course_code, saved.name, str(saved), size, url=url)
        except (DownloadError, SessionError, OSError, ValueError) as exc:
            report.failed.append((filename, str(exc)))
            emit("failed", filename, str(exc))
            continue
        report.saved.append(saved)
        emit("saved", saved.name, f"{size // 1024} KB")
    return report
