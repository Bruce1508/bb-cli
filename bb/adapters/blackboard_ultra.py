from __future__ import annotations

import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rich.console import Console

from bb.adapters.base import Announcement, Deadline, GradeItem, LMSAdapter
from bb.adapters.registry import register
from bb.hash import content_hash
from bb.security.session import SessionManager

_console = Console()

# URL pattern that confirms a successful Blackboard Ultra login
_ULTRA_URL_PATTERN: str = "**/ultra/**"
AUTH_TIMEOUT_MS: int = 300_000  # 5 minutes
STREAM_TIMEOUT_MS: int = 30_000  # 30 seconds
STREAM_PATH: str = "/ultra/stream"
MAX_STREAM_ITEMS: int = 20  # circuit breaker

# Selectors file resolved relative to this file's location (project root / selectors/)
_SELECTORS_PATH: Path = Path(__file__).parent.parent.parent / "selectors" / "blackboard_ultra.toml"


@register("blackboard_ultra")
class BlackboardUltraAdapter(LMSAdapter):
    """Blackboard Ultra adapter — handles auth, scraping, and session management."""

    def __init__(
        self,
        lms_url: str,
        session_manager: SessionManager | None = None,
        selectors_path: Path | None = None,
    ) -> None:
        self._lms_url = lms_url.rstrip("/")
        self._sm = session_manager or SessionManager()
        self._selectors = _load_selectors(selectors_path or _SELECTORS_PATH)

    # ------------------------------------------------------------------
    # LMSAdapter abstract methods
    # ------------------------------------------------------------------

    def authenticate(self) -> None:
        """Open headed Chromium, wait for login + MFA, save encrypted session."""
        # Lazy import — avoids paying Playwright startup cost on every CLI invocation
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(self._lms_url)

            _console.print("\n[bold]Log in to Blackboard in the browser window.[/bold]")
            timeout_s = AUTH_TIMEOUT_MS // 1000
            _console.print(f"[dim]Waiting up to {timeout_s}s for successful login...[/dim]")

            try:
                page.wait_for_url(_ULTRA_URL_PATTERN, timeout=AUTH_TIMEOUT_MS)
            except PlaywrightTimeout:
                browser.close()
                _console.print("[red]Error:[/red] Login timed out after 5 minutes.")
                raise

            # storage_state() returns dict — no path arg to avoid plaintext on disk
            state: dict = context.storage_state()
            browser.close()

        self._sm.encrypt_session(state)
        _console.print("[green]✔[/green] Session saved (encrypted). Expires in ~24h.")

    def check_session(self) -> str:
        """Return 'fresh' | 'uncertain' | 'expired' based on session file age."""
        return self._sm.check_session_age()

    def fetch_activity_stream(self) -> list[Deadline | Announcement | GradeItem]:
        """Scrape the Blackboard Ultra Activity Stream and return typed items.

        Restores the saved browser session (headless), navigates to the stream,
        and parses each item using selectors from blackboard_ultra.toml.

        Raises SessionError if the session file is missing or corrupt.
        Circuit breaker: processes at most MAX_STREAM_ITEMS items per call.
        """
        from playwright.sync_api import sync_playwright

        state = self._sm.decrypt_session()  # raises SessionError if missing/corrupt

        sel = self._selectors.get("activity_stream", {})
        items: list[Deadline | Announcement | GradeItem] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=state)
            page = context.new_page()

            try:
                page.goto(
                    f"{self._lms_url}{STREAM_PATH}",
                    wait_until="networkidle",
                    timeout=STREAM_TIMEOUT_MS,
                )

                # Wait for the stream container — try primary selector then fallback
                container_sel = sel.get("container", "[data-testid='activity-stream-list']")
                container_fallback = sel.get("container_fallback", ".activity-stream-container")
                try:
                    page.wait_for_selector(container_sel, timeout=10_000)
                except Exception:
                    page.wait_for_selector(container_fallback, timeout=10_000)

                # Collect stream item elements — primary then fallback
                item_sel = sel.get("item", "[data-testid='activity-stream-item']")
                item_fallback = sel.get("item_fallback", ".stream-item")
                elements = page.query_selector_all(item_sel)
                if not elements:
                    elements = page.query_selector_all(item_fallback)

                for elem in elements[:MAX_STREAM_ITEMS]:
                    parsed = self._parse_stream_item(elem, sel)
                    if parsed is not None:
                        items.append(parsed)

            finally:
                browser.close()

        return items

    def fetch_grades(self) -> list[GradeItem]:
        """Stub — implemented Day 6."""
        return []

    def fetch_course_content(self, course_id: str) -> object:
        """Stub — implemented Day 8."""
        return {}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_stream_item(
        self, elem: object, sel: dict
    ) -> Deadline | Announcement | GradeItem | None:
        """Parse one activity stream element into a typed data object.

        Type detection strategy (Option A — DOM element presence):
        - Has due-date element  → Deadline
        - Has grade-score element → GradeItem
        - Otherwise             → Announcement
        """
        # Course name
        course_sel = sel.get("course_name", "[analytics-id='stream.entry.course']")
        course_fallback = sel.get("course_name_fallback", ".course-item__name")
        course_elem = elem.query_selector(course_sel) or elem.query_selector(course_fallback)
        course = course_elem.inner_text().strip() if course_elem else "Unknown"

        # Title — required; skip item if missing
        title_sel = sel.get("title", ".name a.js-title-link")
        title_fallback = sel.get("title_fallback", "[data-testid='stream-item-title']")
        title_elem = elem.query_selector(title_sel) or elem.query_selector(title_fallback)
        if title_elem is None:
            return None
        title = title_elem.inner_text().strip()
        if not title:
            return None

        # --- Type detection ---
        due_sel = sel.get("due_date", ".content .due-date bb-translate")
        due_fallback = sel.get("due_date_fallback", "[data-testid='due-date']")
        score_sel = sel.get("score", "[data-testid='grade-score']")
        score_fallback = sel.get("score_fallback", ".grade-score-value")

        due_elem = elem.query_selector(due_sel) or elem.query_selector(due_fallback)
        score_elem = elem.query_selector(score_sel) or elem.query_selector(score_fallback)

        if due_elem:
            due_at = _parse_due_date(due_elem.inner_text().strip())
            return Deadline(
                id=content_hash(course, title, due_at.isoformat()),
                course=course,
                title=title,
                due_at=due_at,
                source="stream",
            )

        if score_elem:
            out_of_sel = sel.get("out_of", "[data-testid='grade-out-of']")
            out_of_fallback = sel.get("out_of_fallback", ".grade-out-of-value")
            out_of_elem = elem.query_selector(out_of_sel) or elem.query_selector(out_of_fallback)
            score = _parse_float(score_elem.inner_text().strip())
            out_of = _parse_float(out_of_elem.inner_text().strip()) if out_of_elem else None
            return GradeItem(
                id=content_hash(course, title, ""),
                course=course,
                item=title,
                score=score,
                out_of=out_of,
                status="graded" if score is not None else "submitted",
            )

        # Announcement — no due date, no grade score
        return Announcement(
            id=content_hash(course, title, ""),
            course=course,
            title=title,
            body="",  # Activity stream shows titles only; full body requires separate page
            posted_at=datetime.now(timezone.utc),
            read_at=None,
        )


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _load_selectors(path: Path) -> dict:
    """Load selectors TOML. Returns empty dict if file is missing."""
    try:
        return tomllib.loads(path.read_text())
    except FileNotFoundError:
        return {}


def _parse_due_date(text: str) -> datetime:
    """Parse a due date string from the Activity Stream DOM into a UTC datetime.

    Handles formats like 'Jan 20, 2026 at 11:59 PM' and 'Jan 20, 2026'.
    Falls back to 7 days from now if the text cannot be parsed.
    """
    text = text.strip().replace(" at ", " ")
    for fmt in (
        "%b %d, %Y %I:%M %p",
        "%b %d, %Y",
        "%B %d, %Y %I:%M %p",
        "%B %d, %Y",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime.now(timezone.utc) + timedelta(days=7)


def _parse_float(text: str) -> float | None:
    """Parse a float from a grade score string. Returns None if unparseable."""
    try:
        return float(text.replace(",", ".").strip())
    except (ValueError, AttributeError):
        return None
