"""Download Blackboard files using authenticated session cookies.

Uses httpx with cookies extracted from the encrypted session file.
No Playwright required — cookies from storage_state JSON work for direct HTTP.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from bb.security.session import SessionManager

LARGE_FILE_BYTES: int = 50 * 1024 * 1024  # 50 MB


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
        cookies = self._extract_cookies()
        try:
            with httpx.Client(
                cookies=cookies,
                timeout=httpx.Timeout(30.0, read=300.0),
                follow_redirects=True,
            ) as client:
                with client.stream("GET", url) as response:
                    response.raise_for_status()
                    content_length = int(response.headers.get("content-length", 0))
                    if content_length > LARGE_FILE_BYTES:
                        import typer

                        mb = content_length / (1024 * 1024)
                        if not typer.confirm(f"  File is {mb:.1f} MB. Download?", default=True):
                            raise DownloadError("Skipped by user (large file)")
                    with open(dest_path, "wb") as f:
                        for chunk in response.iter_bytes():
                            f.write(chunk)
        except httpx.HTTPStatusError as e:
            raise DownloadError(f"HTTP {e.response.status_code}") from e
        except httpx.TimeoutException as e:
            raise DownloadError("Timeout") from e
        except httpx.RequestError as e:
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
