from __future__ import annotations

import tomllib
from pathlib import Path

from rich.console import Console

from bb.adapters.base import Announcement, Deadline, GradeItem, LMSAdapter
from bb.adapters.registry import register
from bb.security.session import SessionManager

_console = Console()

# URL pattern that confirms a successful Blackboard Ultra login
_ULTRA_URL_PATTERN: str = "**/ultra/**"
AUTH_TIMEOUT_MS: int = 300_000  # 5 minutes

# Selectors file resolved relative to this file's location (project root / selectors/)
_SELECTORS_PATH: Path = Path(__file__).parent.parent.parent / "selectors" / "blackboard_ultra.toml"


@register("blackboard_ultra")
class BlackboardUltraAdapter(LMSAdapter):
    """Blackboard Ultra adapter — handles auth and (Day 5+) scraping."""

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
        """Stub — implemented Day 5."""
        return []

    def fetch_grades(self) -> list[GradeItem]:
        """Stub — implemented Day 5."""
        return []

    def fetch_course_content(self, course_id: str) -> object:
        """Stub — implemented Day 6."""
        return {}


# ------------------------------------------------------------------
# Module-level helper (not part of the adapter class)
# ------------------------------------------------------------------

def _load_selectors(path: Path) -> dict:
    """Load selectors TOML. Returns empty dict if file is missing."""
    try:
        return tomllib.loads(path.read_text())
    except FileNotFoundError:
        return {}
