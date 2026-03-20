from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table

import bb.config as _config_module
from bb.config import BBConfig, NotificationConfig, load_config, save_config
from bb.db import Database
from bb.notify.terminal import notify
from bb.parsers.ical import ICalParseError, parse_ical

app = typer.Typer(help="bb — Blackboard LMS terminal client")
console = Console()


@app.command()
def version() -> None:
    """Print the bb-cli version."""
    from bb import __version__

    console.print(f"bb-cli {__version__}")


# (internal_value, display_label)
_LMS_OPTIONS: dict[int, tuple[str, str]] = {
    1: ("blackboard_ultra", "Blackboard Ultra"),
}
_NOTIFY_OPTIONS: dict[int, tuple[str, str]] = {
    1: ("terminal", "Terminal (macOS/Linux native)"),
    2: ("ntfy", "ntfy.sh  [coming soon]"),
    3: ("telegram", "Telegram  [coming soon]"),
    4: ("discord", "Discord  [coming soon]"),
}


@app.command()
def init() -> None:
    """Interactive setup wizard — configure LMS and notifications."""
    existing = load_config()

    # --- LMS type ---
    console.print("\n[bold]LMS type:[/bold]")
    for k, (_, label) in _LMS_OPTIONS.items():
        console.print(f"  ({k}) {label}")
    lms_choice = typer.prompt("Select", default=1, type=int)
    lms_type = _LMS_OPTIONS.get(lms_choice, _LMS_OPTIONS[1])[0]

    # --- LMS URL ---
    lms_url = typer.prompt("LMS URL", default=existing.lms_url)

    # --- Notification method ---
    console.print("\n[bold]Notification method:[/bold]")
    for k, (_, label) in _NOTIFY_OPTIONS.items():
        console.print(f"  ({k}) {label}")
    notify_choice = typer.prompt("Select", default=1, type=int)
    notify_provider = _NOTIFY_OPTIONS.get(notify_choice, _NOTIFY_OPTIONS[1])[0]

    # --- Save config ---
    BB_DIR = _config_module.BB_DIR
    bb_dir_existed = BB_DIR.exists()
    cfg = BBConfig(
        lms_type=lms_type,  # type: ignore[arg-type]
        lms_url=lms_url,
        notification=NotificationConfig(provider=notify_provider),  # type: ignore[arg-type]
        sync_interval_hours=existing.sync_interval_hours,
    )
    save_config(cfg)
    if not bb_dir_existed:
        console.print(f"\n[green]✔[/green] Created {BB_DIR}")
    console.print(f"[green]✔[/green] Config saved to {BB_DIR / 'config.toml'}")

    # --- Initialize database ---
    db_path = BB_DIR / "bb.db"
    with Database(db_path) as db:
        db.setup()
    console.print(f"[green]✔[/green] Database initialized at {db_path}")


@app.command(name="import-ical")
def import_ical(
    url: str = typer.Argument(..., help="iCal feed URL (token-based, no login required)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Parse without writing to DB"),
) -> None:
    """Fetch a Blackboard iCal feed and import deadlines into the database."""
    # --- Fetch ---
    try:
        response = httpx.get(url, follow_redirects=True, timeout=30)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        console.print(f"[red]Error:[/red] server returned HTTP {exc.response.status_code}")
        raise typer.Exit(code=1)
    except httpx.RequestError:
        console.print(f"[red]Error:[/red] could not reach {url}")
        raise typer.Exit(code=1)

    console.print("[green]✔[/green] Fetched iCal feed")

    # --- Parse ---
    try:
        deadlines = parse_ical(response.text)
    except ICalParseError as exc:
        console.print(f"[red]Error:[/red] could not parse iCal feed — {exc}")
        raise typer.Exit(code=1)

    console.print(f"[green]✔[/green] Parsed {len(deadlines)} events")

    # --- Dry run ---
    if dry_run:
        console.print(f"\n[dim][dry-run] Would import {len(deadlines)} deadlines:[/dim]")
        for d in deadlines:
            local_due = d.due_at.astimezone()
            console.print(f"  {d.course} · {d.title} · {local_due.strftime('%Y-%m-%d %H:%M')}")
        return

    # --- Upsert ---
    BB_DIR = _config_module.BB_DIR
    with Database(BB_DIR / "bb.db") as db:
        db.setup()
        new_count = sum(1 for d in deadlines if db.upsert_deadline(d))

    updated_count = len(deadlines) - new_count
    console.print(f"[green]✔[/green] {new_count} new, {updated_count} already up to date")

    # --- Save URL to config so bb sync can reuse it ---
    cfg = load_config()
    if cfg.ical_url != url:
        save_config(cfg.model_copy(update={"ical_url": url}))

    # --- Notify ---
    if new_count > 0:
        label = f"{new_count} new deadline{'s' if new_count != 1 else ''} synced"
        notify("bb", label)
        console.print(f"[blue]🔔[/blue] {label}")


@app.command()
def due(
    days: int = typer.Option(7, "--days", "-d", help="Show deadlines within N days"),
    course: Optional[str] = typer.Option(None, "--course", "-c", help="Filter by course code"),
    all_deadlines: bool = typer.Option(False, "--all", help="Include past-due deadlines"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON array"),
) -> None:
    """Show upcoming deadlines."""
    BB_DIR = _config_module.BB_DIR
    with Database(BB_DIR / "bb.db") as db:
        db.setup()
        deadlines = db.get_upcoming_deadlines(days=days, include_overdue=all_deadlines)

    # --- Filter ---
    if course:
        deadlines = [d for d in deadlines if d.course.upper() == course.upper()]

    # --- JSON output ---
    if output_json:
        data = [
            {
                "id": d.id,
                "course": d.course,
                "title": d.title,
                "due_at": d.due_at.isoformat(),
                "source": d.source,
            }
            for d in deadlines
        ]
        console.print(json.dumps(data, indent=2))
        return

    # --- Empty state ---
    if not deadlines:
        filter_note = f" for {course.upper()}" if course else ""
        console.print(f"No upcoming deadlines in the next {days} days{filter_note}.")
        return

    # --- Rich table ---
    table = Table(show_header=True, header_style="bold")
    table.add_column("Course", style="cyan", min_width=8)
    table.add_column("Assignment", min_width=20)
    table.add_column("Due", min_width=22)

    now = datetime.now(timezone.utc)

    for d in deadlines:
        delta = d.due_at - now
        local_due = d.due_at.astimezone()

        if delta < timedelta(hours=24):
            urgency = "🔴"
            due_style = "bold red"
            if delta.days == 0:
                due_str = f"Tomorrow {local_due.strftime('%I:%M %p')}"
            else:
                due_str = local_due.strftime("%a %b %-d, %H:%M")
        elif delta < timedelta(hours=72):
            urgency = "🟡"
            due_style = "yellow"
            due_str = local_due.strftime("%a %b %-d, %H:%M")
        else:
            urgency = "🟢"
            due_style = "green"
            due_str = local_due.strftime("%a %b %-d, %H:%M")

        table.add_row(
            d.course,
            d.title,
            f"[{due_style}]{urgency} {due_str}[/{due_style}]",
        )

    console.print(table)


@app.command()
def auth() -> None:
    """Open headed Chromium for Blackboard login and save encrypted session."""
    # Local imports — Playwright is heavy; don't pay startup cost for other commands
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    from bb.adapters.blackboard_ultra import BlackboardUltraAdapter  # triggers @register
    from bb.security.session import SessionManager

    cfg = load_config()
    BB_DIR = _config_module.BB_DIR
    sm = SessionManager(BB_DIR / "session.enc")
    adapter = BlackboardUltraAdapter(lms_url=cfg.lms_url, session_manager=sm)

    console.print(f"[bold]Authenticating against:[/bold] {cfg.lms_url}")
    try:
        adapter.authenticate()
    except PlaywrightTimeout:
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command()
def status() -> None:
    """Show session health, last sync time, and DB stats."""
    import sqlite3

    from bb.security.session import SessionManager

    BB_DIR = _config_module.BB_DIR
    sm = SessionManager(BB_DIR / "session.enc")

    # --- Session health ---
    age_status = sm.check_session_age()
    mtime = sm._mtime()
    if age_status == "fresh":
        age_label = "[green]fresh[/green]"
        if mtime:
            hours_ago = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600
            age_label += f" ({hours_ago:.1f}h old)"
    elif age_status == "uncertain":
        age_label = "[yellow]uncertain[/yellow] (run bb sync to verify)"
    else:
        age_label = "[red]expired[/red] — run bb auth"

    console.print(f"[bold]Session:[/bold] {age_label}")

    # --- DB stats ---
    db_path = BB_DIR / "bb.db"
    if not db_path.exists():
        console.print("[bold]DB:[/bold] not initialized — run bb init")
        return

    try:
        with Database(db_path) as db:
            db.setup()
            deadlines = db._conn.execute("SELECT COUNT(*) FROM deadlines").fetchone()[0]
            announcements = db._conn.execute("SELECT COUNT(*) FROM announcements").fetchone()[0]
            grades = db._conn.execute("SELECT COUNT(*) FROM grades").fetchone()[0]
            last_sync_row = db._conn.execute("SELECT MAX(synced_at) FROM sync_log").fetchone()
            last_sync = last_sync_row[0] if last_sync_row and last_sync_row[0] else "never"
    except sqlite3.OperationalError:
        console.print("[bold]DB:[/bold] not initialized — run bb init")
        return

    console.print(f"[bold]Last sync:[/bold] {last_sync}")
    console.print(
        f"[bold]DB:[/bold] {deadlines} deadlines, {announcements} announcements, {grades} grades"
    )


@app.command()
def sync() -> None:
    """Sync deadlines, announcements, and grades from Blackboard."""
    from bb.adapters.blackboard_ultra import BlackboardUltraAdapter
    from bb.security.session import SessionError, SessionManager
    from bb.sync import sync_ical, sync_stream

    cfg = load_config()
    BB_DIR = _config_module.BB_DIR
    db_path = BB_DIR / "bb.db"
    total_new = 0

    # --- Phase 1: iCal ---
    if cfg.ical_url:
        console.print("⟳ Phase 1: iCal sync...")
        try:
            with Database(db_path) as db:
                db.setup()
                new, updated = sync_ical(cfg.ical_url, db)
                db.log_sync("ical", new, updated)
            total_new += new
            console.print(f"[green]✔[/green] {new + updated} deadlines ({new} new)")
        except Exception as exc:
            console.print(f"[yellow]⚠[/yellow] iCal sync failed: {exc}")
    else:
        console.print("[dim]Phase 1: No iCal URL configured — run bb import-ical <url> first[/dim]")

    # --- Phase 2: Activity Stream ---
    console.print("⟳ Phase 2: Activity Stream...")
    sm = SessionManager(BB_DIR / "session.enc")
    adapter = BlackboardUltraAdapter(lms_url=cfg.lms_url, session_manager=sm)
    try:
        with Database(db_path) as db:
            db.setup()
            d_new, a_new, g_new = sync_stream(adapter, db)
            stream_new = d_new + a_new + g_new
            db.log_sync("stream", stream_new, 0)
        total_new += stream_new
        console.print(
            f"[green]✔[/green] {d_new} deadlines, {a_new} announcements, {g_new} grades new"
        )
    except SessionError:
        console.print(
            "[yellow]⚠[/yellow] Session expired. Run [bold]bb auth[/bold] to re-authenticate."
        )
        console.print("[dim]↩ Activity Stream skipped — iCal sync only.[/dim]")
    except Exception as exc:
        console.print(f"[red]Error:[/red] Activity Stream sync failed: {exc}")

    # --- Notify ---
    if total_new > 0:
        label = f"{total_new} new item{'s' if total_new != 1 else ''} synced"
        notify("bb", label)
        console.print(f"[blue]🔔[/blue] {label}")


@app.command()
def ann(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of announcements to show"),
    unread: bool = typer.Option(False, "--unread", help="Show only unread announcements"),
) -> None:
    """Show recent announcements."""
    BB_DIR = _config_module.BB_DIR
    with Database(BB_DIR / "bb.db") as db:
        db.setup()
        announcements = db.get_recent_announcements(limit=limit)

    if unread:
        announcements = [a for a in announcements if a.read_at is None]

    if not announcements:
        msg = "No unread announcements." if unread else "No announcements found."
        console.print(msg)
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Course", style="cyan", min_width=8)
    table.add_column("Announcement", min_width=30)
    table.add_column("Posted", min_width=10)

    now = datetime.now(timezone.utc)
    for a in announcements:
        delta = now - a.posted_at
        if delta.total_seconds() < 3600:
            posted_str = f"{int(delta.total_seconds() / 60)}m ago"
        elif delta.total_seconds() < 86400:
            posted_str = f"{int(delta.total_seconds() / 3600)}h ago"
        else:
            posted_str = f"{delta.days}d ago"

        # Unread announcements shown in bold
        title_str = f"[bold]{a.title}[/bold]" if a.read_at is None else a.title
        table.add_row(a.course, title_str, posted_str)

    console.print(table)
