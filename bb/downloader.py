"""Download Blackboard files using authenticated session cookies.

Uses httpx with cookies extracted from the encrypted session file.
No Playwright required — cookies from storage_state JSON work for direct HTTP.
"""

from __future__ import annotations

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

    def _extract_cookies(self) -> dict[str, str]:
        """Decrypt session → return {name: value} cookie dict for httpx.

        Raises: SessionError if session file missing or corrupt.
        """
        state = self._sm.decrypt_session()  # raises SessionError on failure
        return {c["name"]: c["value"] for c in state.get("cookies", [])}

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


def safe_filename(item: ContentItem) -> str:
    """Filename for a downloaded item: never a path, never hidden, never empty.

    Titles come from Blackboard (untrusted), so path separators are replaced and a
    title made only of dots/spaces (e.g. "..") becomes "file".
    """
    stem = item.title.replace("/", "_").replace("\\", "_").strip()
    if not stem.strip(". "):
        stem = "file"
    return stem.lstrip(".") + ext_from_url(item.download_url)


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
    """Download each item unless a non-empty copy exists; record successes in the DB.

    Failures are collected in the report, never raised, so one bad file can't stop the rest.
    """
    report = DownloadReport()
    emit = on_event or (lambda *_: None)
    for item in items:
        filename = safe_filename(item)
        existing = dest_dir / filename
        if existing.exists() and existing.stat().st_size > 0:
            report.skipped.append(filename)
            emit("skipped", filename, "already downloaded")
            continue
        try:
            saved = downloader.download(item.download_url, dest_dir, filename)
        except (DownloadError, SessionError) as exc:
            report.failed.append((filename, str(exc)))
            emit("failed", filename, str(exc))
            continue
        size = saved.stat().st_size
        db.record_download(course_code, saved.name, str(saved), size)
        report.saved.append(saved)
        emit("saved", saved.name, f"{size // 1024} KB")
    return report
