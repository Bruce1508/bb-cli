from __future__ import annotations

import json
import subprocess
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table

import bb.config as _config_module
from bb.auto_setup import install_auto_sync, uninstall_auto_sync
from bb.config import BBConfig, NotificationConfig, load_config, save_config
from bb.db import Database
from bb.downloader import Downloader, DownloadError
from bb.notify import dispatch_notify
from bb.parsers.ical import ICalParseError, parse_ical

app = typer.Typer(help="bb — Blackboard LMS terminal client")
console = Console()


def _warn_if_session_stale() -> None:
    """Print a one-line warning if session is expired or uncertain."""
    from bb.security.session import SessionManager
    BB_DIR = _config_module.BB_DIR
    sm = SessionManager(BB_DIR / "session.enc")
    age = sm.check_session_age()
    if age == "expired":
        console.print("[yellow]⚠ Session may be expired — run [bold]bb auth[/bold] for fresh data.[/yellow]")
    elif age == "uncertain":
        console.print("[dim]⚠ Session age uncertain — data may be stale. Run bb sync to refresh.[/dim]")


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
        cfg2 = load_config()
        dispatch_notify(cfg2.notification.provider, "bb", label, cfg2.notification.ntfy_topic)
        console.print(f"[blue]🔔[/blue] {label}")


@app.command()
def due(
    days: int = typer.Option(7, "--days", "-d", help="Show deadlines within N days"),
    course: Optional[str] = typer.Option(None, "--course", "-c", help="Filter by course code"),
    all_deadlines: bool = typer.Option(False, "--all", help="Include past-due deadlines"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON array"),
) -> None:
    """Show upcoming deadlines."""
    if not output_json:
        _warn_if_session_stale()
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
            now_local = datetime.now().astimezone()
            if local_due.date() == (now_local + timedelta(days=1)).date():
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

    verified_row = None
    try:
        with Database(db_path) as db:
            db.setup()
            deadlines = db._conn.execute("SELECT COUNT(*) FROM deadlines").fetchone()[0]
            announcements = db._conn.execute("SELECT COUNT(*) FROM announcements").fetchone()[0]
            grade_count = db._conn.execute("SELECT COUNT(*) FROM grades").fetchone()[0]
            sync_rows = db._conn.execute(
                "SELECT synced_at, source, items_new, items_updated, error"
                " FROM sync_log ORDER BY synced_at DESC LIMIT 3"
            ).fetchall()
            verified_row = db._conn.execute(
                "SELECT sent_at FROM notification_log WHERE type='session_verified'"
                " ORDER BY sent_at DESC LIMIT 1"
            ).fetchone()
    except sqlite3.OperationalError:
        console.print("[bold]DB:[/bold] not initialized — run bb init")
        return

    console.print(
        f"[bold]DB:[/bold] {deadlines} deadline{'s' if deadlines != 1 else ''}, "
        f"{announcements} announcement{'s' if announcements != 1 else ''}, "
        f"{grade_count} grade{'s' if grade_count != 1 else ''}"
    )

    if verified_row:
        console.print(f"[bold]Last verified:[/bold] {verified_row[0]}")

    if not sync_rows:
        console.print("[bold]Last syncs:[/bold] never")
    else:
        console.print("[bold]Last syncs:[/bold]")
        for synced_at, source, items_new, items_updated, error in sync_rows:
            status_icon = "[red]✗[/red]" if error else "[green]✔[/green]"
            err_note = f" [red]({error})[/red]" if error else ""
            console.print(
                f"  {status_icon} {synced_at}  [{source}]  "
                f"{items_new} new, {items_updated} updated{err_note}"
            )


@app.command()
def sync(
    ical_only: bool = typer.Option(
        False, "--ical-only", help="Only run Phase 1 (iCal), skip browser scrape"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Fetch iCal and report counts without writing to DB"
    ),
    refresh_only: bool = typer.Option(
        False, "--refresh-only", help="Probe session liveness and exit (no data sync)"
    ),
) -> None:
    """Sync deadlines, announcements, and grades from Blackboard."""
    from bb.adapters.blackboard_ultra import BlackboardUltraAdapter
    from bb.security.session import SessionError, SessionManager
    from bb.sync import preflight_session, sync_announcements, sync_content_additions, sync_grades, sync_ical, sync_stream

    cfg = load_config()
    BB_DIR = _config_module.BB_DIR
    db_path = BB_DIR / "bb.db"
    total_new = 0

    # --- Preflight: verify session liveness before any Playwright work ---
    if not ical_only and not dry_run:
        sm_pre = SessionManager(BB_DIR / "session.enc")
        try:
            with Database(db_path) as db:
                db.setup()
                preflight_session(sm_pre, cfg.lms_url, db)
            if refresh_only:
                console.print("[green]✔[/green] Session verified live.")
                return
        except SessionError as exc:
            console.print(f"[yellow]⚠[/yellow] {exc}")
            with Database(db_path) as db:
                db.setup()
                db.log_sync("preflight", 0, 0, error="session_dead")
                # No cooldown — probe failures need immediate user action
                dispatch_notify(
                    cfg.notification.provider,
                    "bb — Session Expired",
                    "Run `bb auth` to re-authenticate.",
                    cfg.notification.ntfy_topic,
                )
                db.log_notification("session_expired_probe")
            raise typer.Exit(code=1)
    elif refresh_only:
        console.print("[dim]--refresh-only has no effect with --ical-only or --dry-run[/dim]")
        return

    # --- Phase 0: Build course map (skipped if --ical-only) ---
    if not ical_only:
        console.print("⟳ Phase 0: Discovering courses...")
        _t0 = time.monotonic()
        try:
            sm0 = SessionManager(BB_DIR / "session.enc")
            adapter0 = BlackboardUltraAdapter(lms_url=cfg.lms_url, session_manager=sm0)
            course_list = adapter0.fetch_course_list()
            with Database(db_path) as db:
                db.setup()
                for c in course_list:
                    db.upsert_course_map(c["code"], c["bb_id"], c["name"])
            console.print(f"[green]✔[/green] {len(course_list)} courses mapped [{time.monotonic()-_t0:.1f}s]")
        except Exception as exc:
            console.print(f"[yellow]⚠[/yellow] Course discovery failed: {exc} (sync continues)")

    # --- Phase 1: iCal ---
    if cfg.ical_url:
        console.print("⟳ Phase 1: iCal sync...")
        if dry_run:
            try:
                import httpx as _httpx

                from bb.parsers.ical import parse_ical as _parse_ical

                resp = _httpx.get(cfg.ical_url, follow_redirects=True, timeout=30)
                resp.raise_for_status()
                deadlines = _parse_ical(resp.text)
                console.print(
                    f"[dim][dry-run] Would import {len(deadlines)} deadlines from iCal[/dim]"
                )
            except Exception as exc:
                console.print(f"[yellow]⚠[/yellow] iCal fetch failed: {exc}")
            return
        _t1 = time.monotonic()
        try:
            with Database(db_path) as db:
                db.setup()
                new, updated = sync_ical(cfg.ical_url, db)
                db.log_sync("ical", new, updated)
            total_new += new
            console.print(f"[green]✔[/green] {new + updated} deadlines ({new} new) [{time.monotonic()-_t1:.1f}s]")
        except Exception as exc:
            console.print(f"[yellow]⚠[/yellow] iCal sync failed: {exc}")
            with Database(db_path) as db:
                db.setup()
                db.log_sync("ical", 0, 0, error=str(exc))
    else:
        console.print("[dim]Phase 1: No iCal URL configured — run bb import-ical <url> first[/dim]")

    if ical_only or dry_run:
        return

    # --- Phase 2: Activity Stream ---
    console.print("⟳ Phase 2: Activity Stream...")
    _t2 = time.monotonic()
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
            f"[green]✔[/green] {d_new} deadlines, {a_new} announcements, {g_new} grades new [{time.monotonic()-_t2:.1f}s]"
        )
    except SessionError:
        console.print(
            "[yellow]⚠[/yellow] Session expired. Run [bold]bb auth[/bold] to re-authenticate."
        )
        console.print("[dim]↩ Activity Stream skipped — iCal sync only.[/dim]")
        with Database(db_path) as db:
            db.setup()
            db.log_sync("stream", 0, 0, error="session_expired")
            if not db.was_notified_recently("session_expired", within_hours=24):
                dispatch_notify(
                    cfg.notification.provider,
                    "bb — Session Expired",
                    "Run `bb auth` to re-authenticate.",
                    cfg.notification.ntfy_topic,
                )
                db.log_notification("session_expired")
    except Exception as exc:
        console.print(f"[red]Error:[/red] Activity Stream sync failed: {exc}")
        with Database(db_path) as db:
            db.setup()
            db.log_sync("stream", 0, 0, error=str(exc))

    # --- Phase 3: Grades page (catches grades not in activity stream) ---
    if not ical_only and not dry_run:
        console.print("⟳ Phase 3: Grades page...")
        _t3 = time.monotonic()
        sm3 = SessionManager(BB_DIR / "session.enc")
        adapter3 = BlackboardUltraAdapter(lms_url=cfg.lms_url, session_manager=sm3)
        try:
            with Database(db_path) as db:
                db.setup()
                g_new3 = sync_grades(adapter3, db)
                db.log_sync("grades", g_new3, 0)
            total_new += g_new3
            console.print(f"[green]✔[/green] {g_new3} grades new from grades page [{time.monotonic()-_t3:.1f}s]")
        except SessionError:
            console.print("[yellow]⚠[/yellow] Session expired — run [bold]bb auth[/bold].")
        except Exception as exc:
            console.print(f"[yellow]⚠[/yellow] Grades page sync failed: {exc}")

    # --- Phase 4: Course Announcements (REST API — no browser needed) ---
    console.print("⟳ Phase 4: Course announcements...")
    _t4 = time.monotonic()
    sm4 = SessionManager(BB_DIR / "session.enc")
    adapter4 = BlackboardUltraAdapter(lms_url=cfg.lms_url, session_manager=sm4)
    try:
        with Database(db_path) as db:
            db.setup()
            a_new4 = sync_announcements(adapter4, db)
            db.log_sync("announcements", a_new4, 0)
        total_new += a_new4
        console.print(f"[green]✔[/green] {a_new4} announcements new [{time.monotonic()-_t4:.1f}s]")
    except SessionError:
        console.print("[yellow]⚠[/yellow] Session expired — run [bold]bb auth[/bold].")
    except Exception as exc:
        console.print(f"[yellow]⚠[/yellow] Announcements sync failed: {exc}")

    # --- Phase 5: Course Content Additions (REST API, 14-day lookback) ---
    console.print("⟳ Phase 5: Content additions...")
    _t5 = time.monotonic()
    sm5 = SessionManager(BB_DIR / "session.enc")
    adapter5 = BlackboardUltraAdapter(lms_url=cfg.lms_url, session_manager=sm5)
    try:
        with Database(db_path) as db:
            db.setup()
            c_new5 = sync_content_additions(adapter5, db)
            db.log_sync("content", c_new5, 0)
        total_new += c_new5
        console.print(f"[green]✔[/green] {c_new5} content additions new [{time.monotonic()-_t5:.1f}s]")
    except SessionError:
        console.print("[yellow]⚠[/yellow] Session expired — run [bold]bb auth[/bold].")
    except Exception as exc:
        console.print(f"[yellow]⚠[/yellow] Content scan failed: {exc}")

    # --- Notify ---
    if total_new > 0:
        label = f"{total_new} new item{'s' if total_new != 1 else ''} synced"
        dispatch_notify(cfg.notification.provider, "bb", label, cfg.notification.ntfy_topic)
        console.print(f"[blue]🔔[/blue] {label}")


@app.command()
def auto_setup(
    disable: bool = typer.Option(False, "--disable", help="Remove auto-sync scheduler"),
    interval: int = typer.Option(
        0, "--interval", "-i", help="Sync interval in hours (0 = use config value)"
    ),
) -> None:
    """Install (or remove) OS-native auto-sync scheduler."""
    cfg = load_config()
    interval_hours = interval if interval > 0 else cfg.sync_interval_hours

    if disable:
        try:
            platform, msg = uninstall_auto_sync()
            console.print(f"[green]✔[/green] Detected: {platform}")
            console.print(msg)
            console.print("[green]✔[/green] Auto-sync disabled.")
        except RuntimeError as exc:
            console.print(f"[yellow]⚠[/yellow] {exc}")
            raise typer.Exit(code=1)
    else:
        try:
            platform, msg = install_auto_sync(interval_hours=interval_hours)
            console.print(f"[green]✔[/green] Detected: {platform}")
            console.print(msg)
        except RuntimeError as exc:
            console.print(f"[yellow]⚠[/yellow] {exc}")
            raise typer.Exit(code=1)


@app.command()
def grades(
    course: Optional[str] = typer.Option(None, "--course", "-c", help="Filter by course code"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON array"),
) -> None:
    """Show grades from the database."""
    if not output_json:
        _warn_if_session_stale()
    BB_DIR = _config_module.BB_DIR
    with Database(BB_DIR / "bb.db") as db:
        db.setup()
        query = "SELECT id, course, item, score, out_of, status, notified_at FROM grades"
        params: list = []
        if course:
            query += " WHERE UPPER(course) = UPPER(?)"
            params.append(course)
        query += " ORDER BY course, item"
        rows = db._conn.execute(query, params).fetchall()

    if output_json:
        data = [
            {
                "course": r[1],
                "item": r[2],
                "score": r[3],
                "out_of": r[4],
                "status": r[5],
            }
            for r in rows
        ]
        console.print(json.dumps(data, indent=2))
        return

    if not rows:
        filter_note = f" for {course.upper()}" if course else ""
        console.print(f"No grades found{filter_note}.")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Course", style="cyan", min_width=8)
    table.add_column("Assignment", min_width=25)
    table.add_column("Score", min_width=10)
    table.add_column("Status", min_width=10)

    for r in rows:
        _, course_val, item, score, out_of, status, notified_at = r
        # Format score/out_of
        if score is not None and out_of is not None:
            score_str = f"{score:.1f} / {out_of:.1f}"
        elif score is not None:
            score_str = f"{score:.1f}"
        else:
            score_str = "—"

        # Highlight NEW (unnotified graded) items
        is_new = notified_at is None and status == "graded"
        if is_new:
            score_str = f"[bold green]{score_str}[/bold green]"
            item = f"[bold]{item}[/bold]"

        if status == "graded":
            status_style = "green"
        elif status == "submitted":
            status_style = "yellow"
        else:
            status_style = "dim"
        table.add_row(course_val, item, score_str, f"[{status_style}]{status}[/{status_style}]")

    console.print(table)


@app.command()
def ann(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of announcements to show"),
    unread: bool = typer.Option(False, "--unread", help="Show only unread announcements"),
) -> None:
    """Show recent announcements."""
    _warn_if_session_stale()
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


def _render_tree(content_tree) -> None:
    """Display full content tree using Rich Tree widget."""
    from rich.tree import Tree as RichTree

    root = RichTree(
        f"📁 [bold]{content_tree.course_code}[/bold]",
        guide_style="dim",
    )
    for item in content_tree.items:
        _add_tree_node(root, item)
    console.print(root)


def _add_tree_node(parent, item) -> None:
    from bb.models.content import TYPE_ICONS

    icon = TYPE_ICONS.get(item.type, "📄")
    label = f"{icon} {item.title}"
    if item.children:
        label += f"  [dim]({len(item.children)} items)[/dim]"
    node = parent.add(label)
    for child in item.children:
        _add_tree_node(node, child)


def _render_table(content_tree) -> None:
    """Display top-level content items as a Rich table (default view)."""
    from rich.table import Table as _Table

    from bb.models.content import TYPE_ICONS

    table = _Table(
        title=f"📁 {content_tree.course_code}",
        show_header=True,
        header_style="bold",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Type", width=6)
    table.add_column("Title")
    table.add_column("Items", justify="right", style="dim")

    for i, item in enumerate(content_tree.items, start=1):
        icon = TYPE_ICONS.get(item.type, "📄")
        child_count = str(len(item.children)) if item.children else ""
        table.add_row(str(i), icon, item.title, child_count)

    console.print(table)
    console.print(
        f"[dim]Scraped: {content_tree.scraped_at.date()}  "
        "Use [bold]--tree[/bold] for full view.[/dim]"
    )


@app.command()
def course(
    course_code: str = typer.Argument(..., help="Course code, e.g. BTP200"),
    tree: bool = typer.Option(False, "--tree", help="Show full content tree"),
    refresh: bool = typer.Option(False, "--refresh", help="Force re-scrape"),
) -> None:
    """Browse course content."""
    import bb.cache as cache
    from bb.adapters.blackboard_ultra import BlackboardUltraAdapter
    from bb.security.session import SessionManager

    cfg = load_config()
    BB_DIR = _config_module.BB_DIR
    db_path = BB_DIR / "bb.db"

    # 1. Lookup bb_id
    with Database(db_path) as db:
        db.setup()
        bb_id = db.get_course_bb_id(course_code.upper())

    if not bb_id:
        console.print(
            f"[yellow]⚠[/yellow] Course [bold]{course_code.upper()}[/bold] not found. "
            "Run [bold]bb sync[/bold] first to discover courses."
        )
        raise typer.Exit(1)

    # 2. Cache decision
    content_tree = None

    if not refresh and (content_tree := cache.load_tree(course_code)) is not None:
        # Cache exists — warn if stale, but use it either way
        if not cache.is_fresh(course_code):
            console.print(
                f"[dim]Cache is stale. Run [bold]bb course {course_code.upper()} --refresh"
                "[/bold] to update.[/dim]"
            )
    else:
        # No cache or --refresh requested — scrape
        console.print(f"[dim]⟳ Scraping {course_code.upper()} content...[/dim]")
        sm = SessionManager(BB_DIR / "session.enc")
        adapter = BlackboardUltraAdapter(lms_url=cfg.lms_url, session_manager=sm)
        try:
            content_tree = adapter.fetch_course_content(course_code.upper(), bb_id)
            cache.save_tree(content_tree)
        except Exception as exc:
            console.print(f"[red]✘[/red] Scrape failed: {exc}")
            raise typer.Exit(1)

    # 3. Display
    if tree:
        _render_tree(content_tree)
    else:
        _render_table(content_tree)


@app.command()
def cache_clear(
    course_code: Optional[str] = typer.Argument(None, help="Course to clear (default: all)"),
) -> None:
    """Clear cached course content."""
    import bb.cache as cache

    count = cache.clear(course_code)
    if count == 0:
        console.print("[dim]No cache to clear.[/dim]")
    elif course_code:
        console.print(f"[green]✔[/green] Cleared cache for {course_code.upper()}.")
    else:
        console.print(f"[green]✔[/green] Cleared cache for {count} course(s).")


def _ext_from_url(url: str | None) -> str:
    """Extract file extension from URL: 'https://host/file.pdf?x=1' → '.pdf'."""
    if not url:
        return ""
    path_part = url.split("?")[0].split("/")[-1]
    return ("." + path_part.rsplit(".", 1)[-1]) if "." in path_part else ""


def _collect_downloadable(items: list) -> list:
    """DFS: return all ContentItems that have a download_url set."""
    result = []
    for item in items:
        if item.download_url:
            result.append(item)
        result.extend(_collect_downloadable(item.children))
    return result


def _find_items_by_title(items: list, query: str) -> list:
    """DFS: return all ContentItems whose title contains query (case-insensitive)."""
    result = []
    for item in items:
        if query.lower() in item.title.lower():
            result.append(item)
        result.extend(_find_items_by_title(item.children, query))
    return result


@app.command()
def download(
    course_code: str = typer.Argument(..., help="Course code, e.g. BTP200"),
    all_files: bool = typer.Option(False, "--all", help="Download all downloadable files"),
    file_type: str | None = typer.Option(None, "--type", help="Filter by type: pdf, html, etc."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be downloaded"),
    item_name: str | None = typer.Argument(None, help="Specific item name (substring match)"),
) -> None:
    """Download course files to ~/.bb/files/<COURSE>/."""
    import bb.cache as cache
    from bb.security.session import SessionError, SessionManager

    BB_DIR = _config_module.BB_DIR
    tree = cache.load_tree(course_code)
    if tree is None:
        console.print(
            f"[red]✘[/red] No cache for [bold]{course_code.upper()}[/bold]. "
            f"Run [bold]bb course {course_code.upper()}[/bold] first."
        )
        raise typer.Exit(1)

    candidates = _collect_downloadable(tree.items)

    # Require --all or item_name
    if not all_files and not item_name:
        console.print(
            "[yellow]Specify [bold]--all[/bold] to download everything, "
            "[bold]--type pdf[/bold] to filter by type, "
            "or provide an item name.[/yellow]"
        )
        raise typer.Exit(0)

    # Apply --type filter: extension-first, mime_type fallback
    if file_type:
        ft = file_type.lower()

        def _type_match(item) -> bool:
            ext = _ext_from_url(item.download_url).lstrip(".")
            if ext == ft:
                return True
            return bool(item.mime_type and ft in item.mime_type.lower())

        candidates = [i for i in candidates if _type_match(i)]

    # Apply item name filter
    if item_name:
        candidates = [i for i in candidates if item_name.lower() in i.title.lower()]

    if not candidates:
        console.print("[yellow]No downloadable files found matching criteria.[/yellow]")
        raise typer.Exit(0)

    if dry_run:
        console.print(f"[bold]Would download {len(candidates)} file(s):[/bold]")
        for item in candidates:
            ext = _ext_from_url(item.download_url)
            console.print(f"  {item.title}{ext}")
        raise typer.Exit(0)

    dest_dir = BB_DIR / "files" / course_code.upper()
    sm = SessionManager(BB_DIR / "session.enc")
    downloader = Downloader(sm)
    downloaded = skipped = failed = 0

    console.print(f"📥 [bold]{course_code.upper()}[/bold] — Downloading files")

    with Database(BB_DIR / "bb.db") as db:
        db.setup()
        for item in candidates:
            ext = _ext_from_url(item.download_url)
            filename = item.title.replace("/", "_") + ext
            dest_check = dest_dir / filename

            if dest_check.exists() and dest_check.stat().st_size > 0:
                console.print(f"  [dim]⏩ {filename}  already downloaded[/dim]")
                skipped += 1
                continue

            try:
                saved = downloader.download(item.download_url, dest_dir, filename)
                size = saved.stat().st_size
                db.record_download(course_code, saved.name, str(saved), size)
                console.print(f"  [green]✔[/green] {saved.name}  {size // 1024} KB")
                downloaded += 1
            except (DownloadError, SessionError) as e:
                console.print(f"  [yellow]⚠[/yellow]  {filename}  {e}")
                failed += 1

    console.print(
        f"[green]✔[/green] {downloaded} downloaded, {skipped} skipped, {failed} failed"
        f"  →  [dim]{dest_dir}[/dim]"
    )


@app.command(name="open")
def open_item(
    course_code: str = typer.Argument(..., help="Course code, e.g. BTP200"),
    item_name: str = typer.Argument(..., help="Item title (substring match)"),
) -> None:
    """Open a course item in the browser."""
    import bb.cache as cache

    tree = cache.load_tree(course_code)
    if tree is None:
        console.print(
            f"[red]✘[/red] No cache for [bold]{course_code.upper()}[/bold]. "
            f"Run [bold]bb course {course_code.upper()}[/bold] first."
        )
        raise typer.Exit(1)

    matches = _find_items_by_title(tree.items, item_name)

    if not matches:
        console.print(f"[yellow]No item matching '[bold]{item_name}[/bold]' found.[/yellow]")
        console.print("Available items:")
        for item in tree.items:
            console.print(f"  • {item.title}")
        raise typer.Exit(1)

    item = matches[0]

    if item.url is None:
        console.print(f"[yellow]No URL available for '[bold]{item.title}[/bold]'.[/yellow]")
        raise typer.Exit(1)

    console.print(f"→ Opening in browser: [dim]{item.url}[/dim]")
    webbrowser.open(item.url)


@app.command()
def chat(
    query: Optional[str] = typer.Argument(None, help="Ask a single question (omit for REPL)"),
) -> None:
    """Chat with your AI assistant — ask about deadlines, grades, and course content."""
    from bb.ai.chat import run_chat
    run_chat(query=query, cfg=load_config(), console=console)


@app.command(name="mcp-server")
def mcp_server_cmd() -> None:
    """Start MCP server for Claude Desktop / Cursor integration (stdio transport)."""
    from bb.mcp.server import run
    run()


@app.command("setup-browsers")
def setup_browsers() -> None:
    """Install Chromium browser required for Blackboard scraping (bb auth, bb sync)."""
    result = subprocess.run(["playwright", "install", "chromium"], check=False)
    if result.returncode != 0:
        raise typer.Exit(1)
