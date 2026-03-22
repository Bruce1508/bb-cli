from __future__ import annotations

import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from bb.models.content import ContentTree

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

                # Capture page HTML for snapshot when 0 items scraped
                self._last_page_html = page.content() if not items else None

            finally:
                browser.close()

        return items

    def fetch_grades(self) -> list[GradeItem]:
        """Scrape the Blackboard Ultra Grades page and return typed GradeItem objects.

        Navigates to /ultra/grades (headless), parses each grade row using
        selectors from blackboard_ultra.toml.

        Raises SessionError if the session file is missing or corrupt.
        """
        from playwright.sync_api import sync_playwright

        state = self._sm.decrypt_session()  # raises SessionError if missing/corrupt

        sel = self._selectors.get("grades", {})
        grades_path = sel.get("grades_path", "/ultra/grades")
        items: list[GradeItem] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=state)
            page = context.new_page()

            try:
                page.goto(
                    f"{self._lms_url}{grades_path}",
                    wait_until="networkidle",
                    timeout=STREAM_TIMEOUT_MS,
                )

                row_sel = sel.get("grade_row", "[data-testid='grade-row']")
                row_fallback = sel.get("grade_row_fallback", ".graded-item-row")
                rows = page.query_selector_all(row_sel)
                if not rows:
                    rows = page.query_selector_all(row_fallback)

                for row in rows[:MAX_STREAM_ITEMS]:
                    item = self._parse_grade_row(row, sel)
                    if item is not None:
                        items.append(item)

            finally:
                browser.close()

        return items

    def _parse_grade_row(self, row: object, sel: dict) -> GradeItem | None:
        """Parse one grades-page row into a GradeItem.

        Returns None if the row is missing a title (malformed / header row).
        """
        # Course name
        course_sel = sel.get("course_name", "[data-testid='grade-course-name']")
        course_fallback = sel.get("course_name_fallback", ".course-name")
        course_elem = row.query_selector(course_sel) or row.query_selector(course_fallback)
        course = course_elem.inner_text().strip() if course_elem else "Unknown"

        # Item title — required
        title_sel = sel.get("item_title", "[data-testid='grade-item-title']")
        title_fallback = sel.get("item_title_fallback", ".grade-item-title")
        title_elem = row.query_selector(title_sel) or row.query_selector(title_fallback)
        if title_elem is None:
            return None
        title = title_elem.inner_text().strip()
        if not title:
            return None

        # Score
        score_sel = sel.get("score", "[data-testid='grade-score']")
        score_fallback = sel.get("score_fallback", ".grade-score-value")
        score_elem = row.query_selector(score_sel) or row.query_selector(score_fallback)
        score = _parse_float(score_elem.inner_text().strip()) if score_elem else None

        # Out-of denominator
        out_of_sel = sel.get("out_of", "[data-testid='grade-out-of']")
        out_of_fallback = sel.get("out_of_fallback", ".grade-out-of-value")
        out_of_elem = row.query_selector(out_of_sel) or row.query_selector(out_of_fallback)
        out_of = _parse_float(out_of_elem.inner_text().strip()) if out_of_elem else None

        # Status badge
        status_sel = sel.get("status", "[data-testid='grade-status']")
        status_fallback = sel.get("status_fallback", ".grade-status-label")
        status_elem = row.query_selector(status_sel) or row.query_selector(status_fallback)
        raw_status = status_elem.inner_text().strip().lower() if status_elem else ""
        if "graded" in raw_status or score is not None:
            status = "graded"
        elif "submitted" in raw_status:
            status = "submitted"
        else:
            status = "pending"

        return GradeItem(
            id=content_hash(course, title, ""),
            course=course,
            item=title,
            score=score,
            out_of=out_of,
            status=status,
        )

    def fetch_course_list(self) -> list[dict]:
        """Scrape course list → list of {code, bb_id, name}.

        Uses the activity stream page — extracts unique course links from
        [analytics-id='stream.entry.course'] anchors. Only returns courses
        with recent activity in the stream.
        """
        import re as _re

        from playwright.sync_api import sync_playwright

        state = self._sm.decrypt_session()
        stream_sel = self._selectors.get("activity_stream", {})
        container_sel = stream_sel.get("container", "#activity-stream")

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
                page.wait_for_selector(container_sel, timeout=15_000)

                seen: dict[str, dict] = {}
                for link in page.query_selector_all("[analytics-id='stream.entry.course']"):
                    href = link.get_attribute("href") or ""
                    parts = [s for s in href.split("/") if _re.match(r"^_\d+_\d+$", s)]
                    if not parts:
                        continue
                    bb_id = parts[0]
                    if bb_id in seen:
                        continue
                    raw = link.inner_text().strip()
                    m = _re.search(r"\(([^)]+)\)", raw)
                    if m:
                        code = m.group(1).split(".")[0].upper()
                        name = raw[: raw.rfind("(")].strip()
                    else:
                        code = raw.split()[0].upper()
                        name = raw
                    seen[bb_id] = {"code": code, "bb_id": bb_id, "name": name}
                return list(seen.values())
            finally:
                browser.close()

    def fetch_course_content(self, course_code: str, course_bb_id: str) -> "ContentTree":
        """DFS scrape of course outline page → ContentTree.

        Args:
            course_code:   Human-readable code e.g. "BTP200" (stored in ContentTree)
            course_bb_id:  Blackboard internal ID e.g. "_773522_1" (used in URL)

        Circuit breaker: max 200 items total, max depth 5.
        On individual item failure: skip + continue (never crash full scrape).
        """
        from datetime import datetime, timezone

        from playwright.sync_api import sync_playwright

        from bb.models.content import ContentTree

        state = self._sm.decrypt_session()  # raises SessionError if missing/corrupt
        sel = self._selectors.get("course_content", {})

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=state)
            page = context.new_page()
            try:
                url = f"{self._lms_url}/ultra/courses/{course_bb_id}/outline"
                page.goto(url, wait_until="load")
                # content_list may be empty (no container wrapper) — fall back to item
                _wait_sel = sel.get("content_list") or sel.get(
                    "content_item", "[data-content-id]"
                )
                page.wait_for_selector(_wait_sel, timeout=20_000)

                counter = {"total": 0}
                items = _scrape_content_level(page, page, sel, depth=0, counter=counter)
            finally:
                browser.close()

        return ContentTree(
            course_code=course_code.upper(),
            course_bb_id=course_bb_id,
            scraped_at=datetime.now(timezone.utc),  # serialized in content_tree_to_dict
            items=items,
        )

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
        # Course name — text is "Display Name (CODE.SECTION.YEAR)", extract base code
        import re as _re_local
        course_sel = sel.get("course_name", "[analytics-id='stream.entry.course']")
        course_fallback = sel.get("course_name_fallback", ".course-item__name")
        course_elem = elem.query_selector(course_sel) or elem.query_selector(course_fallback)
        if course_elem:
            raw = course_elem.inner_text().strip()
            m = _re_local.search(r"\(([^)]+)\)", raw)
            course = m.group(1).split(".")[0].upper() if m else raw.split()[0].upper()
        else:
            course = "Unknown"

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

    Handles formats including:
    - 'Jan 20, 2026 at 11:59 PM'
    - 'Jan 20, 2026'
    - '3/27/26, 11:59 PM (EDT)'   ← Seneca Blackboard Ultra format
    - '3/27/26, 11:59 PM'

    Falls back to 7 days from now if the text cannot be parsed.
    """
    import re as _re

    # Strip "Due Date: " / "Due: " prefixes
    text = _re.sub(r"^Due\s*(Date)?:\s*", "", text.strip(), flags=_re.IGNORECASE)
    # Strip trailing timezone like " (EDT)" or " (EST)"
    text = _re.sub(r"\s*\([A-Z]{2,4}\)\s*$", "", text)
    text = text.strip().replace(" at ", " ")

    for fmt in (
        "%m/%d/%y, %I:%M %p",   # 3/27/26, 11:59 PM  ← Seneca format
        "%m/%d/%Y, %I:%M %p",  # 3/27/2026, 11:59 PM
        "%m/%d/%y",             # 3/27/26
        "%b %d, %Y %I:%M %p",  # Jan 20, 2026 11:59 PM
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


MAX_ITEMS = 200
MAX_DEPTH = 5


def _parse_content_item(el, sel: dict):
    """Parse one content element → ContentItem.

    Module-level helper — called by _scrape_content_level.
    """
    from bb.models.content import ContentItem

    title_el = el.query_selector(sel.get("content_item_title", ".content-title")) or el.query_selector(
        sel.get("content_item_title_fallback", "h2, h3, h4")
    )
    title = title_el.inner_text().strip() if title_el else "Untitled"

    # Detect type — expand button presence is the most reliable signal for folders
    item_type = "file"  # default
    type_attr = el.get_attribute("data-content-type") or ""
    class_attr = el.get_attribute("class") or ""
    expand_sel = sel.get("expand_button", "")
    expand_sel_fb = sel.get("expand_button_fallback", "")

    if expand_sel and el.query_selector(expand_sel):
        item_type = "folder"
    elif expand_sel_fb and el.query_selector(expand_sel_fb):
        item_type = "folder"
    elif type_attr:
        item_type = type_attr.lower()
    elif "module" in class_attr or "folder" in class_attr:
        item_type = "module"
    elif "discussion" in class_attr:
        item_type = "discussion"
    elif "link" in class_attr or "externalLink" in class_attr:
        item_type = "link"
    elif "assignment" in class_attr or "assessment" in class_attr:
        item_type = "assignment"

    # Download URL — follow existing two-selector resilience pattern
    file_sel = sel.get("file_link", "[data-testid='file-attachment-link']")
    file_sel_fb = sel.get("file_link_fallback", "a[href*='/bbcswebdav/']")
    link_el = el.query_selector(file_sel) or el.query_selector(file_sel_fb)
    download_url = link_el.get_attribute("href") if link_el else None

    # View URL
    view_el = el.query_selector("a[href*='/ultra/']")
    url = view_el.get_attribute("href") if view_el else None

    return ContentItem(
        type=item_type,
        title=title,
        url=url,
        download_url=download_url,
    )


def _scrape_content_level(
    root,           # page OR ElementHandle — both support .query_selector_all()
    page,           # always the Page object — needed for wait_for_timeout()
    sel: dict,
    depth: int,
    counter: dict,
) -> list:
    """DFS scrape of one level of content items, recursing into modules/folders.

    Module-level helper — called by BlackboardUltraAdapter.fetch_course_content.

    Args:
        root:    The DOM root to query — Page on first call, ElementHandle on recursion.
                 Both Page and ElementHandle support .query_selector_all() in Playwright.
        page:    Always the top-level Page object (needed for wait_for_timeout).
        sel:     Selector dict from blackboard_ultra.toml [course_content] section.
        depth:   Current recursion depth (0 = top-level).
        counter: Mutable dict {"total": int} — shared across all recursion levels.

    Returns list[ContentItem].
    """
    if depth >= MAX_DEPTH or counter["total"] >= MAX_ITEMS:
        return []

    items = []
    elements = root.query_selector_all(
        sel.get("content_item", "[data-testid='content-item']")
    )

    for el in elements:
        if counter["total"] >= MAX_ITEMS:
            break
        try:
            item = _parse_content_item(el, sel)
        except Exception:
            continue  # Skip unparseable items — never crash full scrape

        counter["total"] += 1

        if item.type in ("module", "folder"):
            # Try to expand collapsed module/folder
            expand_btn = el.query_selector(
                sel.get("expand_button", "[data-testid='content-item-expand']")
            )
            if expand_btn:
                try:
                    expand_btn.click()
                    page.wait_for_timeout(800)  # wait for children to render in DOM
                except Exception:
                    pass

            # Recurse into folder children — try named container first,
            # fall back to querying content_item directly on the element itself.
            _container_sel = sel.get("content_list")
            nested = el.query_selector(_container_sel) if _container_sel else None
            if nested:
                item.children = _scrape_content_level(
                    nested, page, sel, depth + 1, counter
                )
            elif el.query_selector(sel.get("content_item", "[data-content-id]")):
                # Children are DOM-children of the item element (no wrapper div)
                item.children = _scrape_content_level(
                    el, page, sel, depth + 1, counter
                )

        items.append(item)

    return items
