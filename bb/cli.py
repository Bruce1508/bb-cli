from __future__ import annotations

import json
import re
import subprocess
import time
import webbrowser
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

import bb.config as _config_module
from bb.auto_setup import install_auto_sync, uninstall_auto_sync
from bb.config import BBConfig, NotificationConfig, load_config, save_config
from bb.db import Database
from bb.downloader import Downloader, collect_downloadable, download_items, ext_from_url
from bb.notify import dispatch_notify
from bb.parsers.ical import ICalParseError, parse_ical

app = typer.Typer(help="bb — Blackboard LMS terminal client")
console = Console()


@app.callback(invoke_without_command=True)
def _main(ctx: typer.Context) -> None:
    """bb — Blackboard in your terminal. Run `bb` alone to see what matters today."""
    if ctx.invoked_subcommand is None:
        today()


def _warn_if_session_stale() -> None:
    """Print a one-line warning if session is expired or uncertain."""
    from bb.security.session import SessionManager
    BB_DIR = _config_module.BB_DIR
    sm = SessionManager(BB_DIR / "session.enc")
    age = sm.check_session_age()
    if age == "expired":
        console.print(
            "[yellow]⚠ Session may be expired — run [bold]bb auth[/bold] for fresh data.[/yellow]"
        )
    elif age == "uncertain":
        console.print(
            "[dim]⚠ Session age uncertain — data may be stale. Run bb sync to refresh.[/dim]"
        )


_CHANGE_COOLDOWN_HOURS = 6
_NOTIFY_CHANGE_TYPES = {"due_moved", "grade_posted", "grade_changed"}


def _render_change_digest(changes: list) -> str:
    """Return a one-line '⟳ N changes: ...' digest, or '' when empty."""
    from bb.changes import humanize

    if not changes:
        return ""
    n = len(changes)
    return f"⟳ {n} change{'s' if n != 1 else ''}: {humanize(changes)}"


def _notify_changes(db, changes, ncfg) -> None:
    """Fire one deduped notification per changed item+field (6h cooldown)."""
    from bb.changes import humanize

    for ch in changes:
        if ch.change_type not in _NOTIFY_CHANGE_TYPES:
            continue
        key = f"change:{ch.item_id}:{ch.field}"
        if db.was_notified_recently(key, within_hours=_CHANGE_COOLDOWN_HOURS):
            continue
        dispatch_notify(ncfg, "bb", humanize([ch]), priority="high")
        db.log_notification(key)


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
    1: ("terminal", "Desktop notification (this computer only)"),
    2: ("ntfy", "ntfy.sh — phone push, no account needed (recommended)"),
    3: ("telegram", "Telegram bot"),
    4: ("discord", "Discord webhook"),
}


def _prompt_notification_details(
    current: NotificationConfig, provider: str
) -> NotificationConfig:
    """Ask only for the credentials the chosen provider needs; keep everything else."""
    import secrets

    n = current.model_copy(update={"provider": provider})
    keep_hint = "[dim](press Enter to keep the saved one)[/dim]"
    if provider == "ntfy":
        default_topic = n.ntfy_topic or f"bb-{secrets.token_hex(4)}"
        while True:
            topic = typer.prompt(
                "ntfy topic (anyone who knows it can read it)", default=default_topic
            ).strip()
            if re.fullmatch(r"[-_A-Za-z0-9]{1,64}", topic):
                break
            console.print("[red]Use 1-64 letters, digits, '-' or '_' only.[/red]")
        n = n.model_copy(update={"ntfy_topic": topic})
        console.print(f"[dim]  Install the ntfy app and subscribe to: {escape(topic)}[/dim]")
    elif provider == "telegram":
        if n.telegram_token:
            console.print(keep_hint)
        token = typer.prompt(
            "Telegram bot token (from @BotFather)",
            default=n.telegram_token or None,
            hide_input=True,
            show_default=False,
        )
        chat_id = typer.prompt("Telegram chat id", default=n.telegram_chat_id or None)
        n = n.model_copy(
            update={"telegram_token": token.strip(), "telegram_chat_id": chat_id.strip()}
        )
    elif provider == "discord":
        if n.discord_webhook:
            console.print(keep_hint)
        hook = typer.prompt(
            "Discord webhook URL", default=n.discord_webhook or None, show_default=False
        )
        n = n.model_copy(update={"discord_webhook": hook.strip()})
    return n


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
    saved_choice = next(
        (k for k, (p, _) in _NOTIFY_OPTIONS.items() if p == existing.notification.provider), 1
    )
    notify_choice = typer.prompt("Select", default=saved_choice, type=int)
    notify_provider = _NOTIFY_OPTIONS.get(notify_choice, _NOTIFY_OPTIONS[1])[0]
    notification = _prompt_notification_details(existing.notification, notify_provider)

    # --- iCal feed URL ---
    console.print(
        "\n[bold]iCal feed URL[/bold] [dim](optional — enables deadline sync without browser)[/dim]"
    )
    console.print(
        "[dim]  Find it in Blackboard → Calendar → Subscribe → copy the URL[/dim]"
    )
    ical_url = typer.prompt("iCal URL (leave blank to skip)", default=existing.ical_url or "")
    ical_url = ical_url.strip() or None

    # --- Save config (update the existing one — never drop [ai] or tokens) ---
    BB_DIR = _config_module.BB_DIR
    bb_dir_existed = BB_DIR.exists()
    cfg = existing.model_copy(update={
        "lms_type": lms_type,
        "lms_url": lms_url,
        "ical_url": ical_url,
        "notification": notification,
    })
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
        dispatch_notify(cfg2.notification, "bb", label)
        console.print(f"[blue]🔔[/blue] {label}")


@app.command()
def today() -> None:
    """Show what matters today: urgent deadlines, changes, unread announcements."""
    from bb.tools.queries import get_briefing

    # No config.toml = never set up. Not "no successful sync": `bb import-ical` writes
    # config + deadlines without a sync_log row, and failing syncs log only errors —
    # those users must see their stored deadlines, not be sent back to `bb setup`.
    if not (_config_module.BB_DIR / "config.toml").exists():
        console.print("👋 Not set up yet — run [bold]bb setup[/bold] to connect Blackboard.")
        return
    _warn_if_session_stale()
    _render_briefing(get_briefing())


def _render_briefing(b: dict) -> None:
    if b.get("last_sync"):
        local = datetime.fromisoformat(b["last_sync"]).astimezone()
        sync_note = f"synced {local.strftime('%a %b %-d %H:%M')}"
    else:
        sync_note = "never synced — run bb sync"
    console.print(f"[bold]📅 Today[/bold]  [dim]({sync_note})[/dim]")

    urgent = b["urgent_deadlines"]
    if urgent:
        for d in urgent:
            console.print(
                f"  🔴 [cyan]{escape(d['course'])}[/cyan] {escape(d['title'])}"
                f" — [bold]{d['when']}[/bold]"
            )
    else:
        console.print("  [green]Nothing due in the next 48h.[/green]")
    if b["later_this_week"]:
        console.print(f"  [dim]+{b['later_this_week']} more this week → bb due[/dim]")

    for c in b["recent_changes"][:5]:
        console.print(
            f"  ⟳ [cyan]{escape(c['course'])}[/cyan] {escape(c['title'])}:"
            f" {c['change_type'].replace('_', ' ')}"
        )
    for a in b["unread_announcements"]:
        console.print(f"  📢 [cyan]{escape(a['course'])}[/cyan] {escape(a['title'])}")
    extra = b.get("unread_count", 0) - len(b["unread_announcements"])
    if extra > 0:
        console.print(f"  [dim]+{extra} more unread → bb ann[/dim]")
    elif b["unread_announcements"]:
        console.print("  [dim]→ bb ann to read them[/dim]")


@app.command()
def due(
    days: int = typer.Option(7, "--days", "-d", help="Show deadlines within N days"),
    course: Optional[str] = typer.Option(None, "--course", "-c", help="Filter by course code"),
    all_deadlines: bool = typer.Option(False, "--all", help="Include past-due deadlines"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON array"),
) -> None:
    """Show upcoming deadlines."""
    course = _course_arg(course)
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
            age_label += f" ({hours_ago:.1f}h old) — next: [dim]bb sync[/dim]"
    elif age_status == "uncertain":
        age_label = "[yellow]uncertain[/yellow] — run [bold]bb sync --refresh-only[/bold] to verify"
    else:
        age_label = "[red]expired[/red] — run [bold]bb auth[/bold] then [bold]bb sync[/bold]"

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


def _run_proactive(cfg: BBConfig, db_path: Path, digest: bool = True) -> None:
    """Send due-soon reminders and the daily digest (each deduped). Never fails the sync."""
    from bb.briefing import send_daily_digest
    from bb.reminders import send_reminders

    try:
        with Database(db_path) as db:
            db.setup()
            n = send_reminders(db, cfg.notification)
        if n:
            console.print(f"[blue]⏰[/blue] {n} deadline reminder{'s' if n != 1 else ''} sent")
    except Exception as exc:
        console.print(f"[yellow]⚠[/yellow] Reminders failed: {exc}")

    if not digest:
        return
    try:
        with Database(db_path) as db:
            db.setup()
            digest_sent = send_daily_digest(db, cfg.notification)
        if digest_sent:
            console.print("[blue]🔔[/blue] Daily digest sent")
    except Exception as exc:
        console.print(f"[yellow]⚠[/yellow] Daily digest failed: {exc}")


@contextmanager
def _sync_lock():
    """Exclusive, non-blocking lock so a chat/MCP sync can't race the scheduled one.

    Yields True when acquired. The lock is released when the file closes (also on crash).
    Platforms without fcntl (Windows) yield True — auto-sync isn't supported there anyway.
    """
    try:
        import fcntl
    except ImportError:
        yield True
        return
    bb_dir = _config_module.BB_DIR
    bb_dir.mkdir(parents=True, exist_ok=True)
    with open(bb_dir / "sync.lock", "w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True


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
    with _sync_lock() as acquired:
        if not acquired:
            console.print("[dim]Another bb sync is running — skipped.[/dim]")
            return
        _run_sync(ical_only=ical_only, dry_run=dry_run, refresh_only=refresh_only)


def _course_arg(text: str | None) -> str | None:
    """Resolve a user-typed course ('btp', 'oop') to a course code (lazy import: fast startup)."""
    from bb.tools.queries import resolve_course

    return resolve_course(text)


def _run_sync(ical_only: bool, dry_run: bool, refresh_only: bool) -> None:
    from bb.adapters.blackboard_ultra import BlackboardUltraAdapter
    from bb.security.session import SessionError, SessionManager
    from bb.sync import (
        preflight_session,
        sync_announcements,
        sync_content_additions,
        sync_grades,
        sync_ical,
        sync_stream,
    )

    cfg = load_config()
    BB_DIR = _config_module.BB_DIR
    db_path = BB_DIR / "bb.db"
    total_new = 0
    session_dead = False

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
            console.print(f"[red]✘[/red] {exc}")
            if not refresh_only:
                console.print(
                    "[dim]↩ Session expired — syncing deadlines from iCal only. "
                    "Run bb auth for grades and announcements.[/dim]"
                )
            with Database(db_path) as db:
                db.setup()
                db.log_sync("preflight", 0, 0, error="session_dead")
                # No cooldown — probe failures need immediate user action
                dispatch_notify(
                    cfg.notification,
                    "bb — Session Expired",
                    "Run `bb auth` to re-authenticate.",
                    priority="high",
                )
                db.log_notification("session_expired_probe")
            if refresh_only:  # liveness probe only
                raise typer.Exit(code=1)
            session_dead = True
            ical_only = True  # iCal needs no auth; fall through to Phase 1
    elif refresh_only:
        console.print("[dim]--refresh-only has no effect with --ical-only or --dry-run[/dim]")
        return

    run_start = datetime.now(timezone.utc).isoformat()

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
            console.print(
                f"[green]✔[/green] {len(course_list)} courses mapped "
                f"[{time.monotonic()-_t0:.1f}s]"
            )
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
            console.print(
                f"[green]✔[/green] {new + updated} deadlines ({new} new) "
                f"[{time.monotonic()-_t1:.1f}s]"
            )
        except Exception as exc:
            console.print(f"[yellow]⚠[/yellow] iCal sync failed: {exc}")
            with Database(db_path) as db:
                db.setup()
                db.log_sync("ical", 0, 0, error=str(exc))
    else:
        console.print("[dim]Phase 1: No iCal URL configured — run bb import-ical <url> first[/dim]")

    if not dry_run:
        # full sync: the digest waits for the end-of-sync call, after all phases
        _run_proactive(cfg, db_path, digest=ical_only)
    if ical_only or dry_run:
        if session_dead:
            raise typer.Exit(code=1)
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
            f"[green]✔[/green] {d_new} deadlines, {a_new} announcements, {g_new} grades new "
            f"[{time.monotonic()-_t2:.1f}s]"
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
                    cfg.notification,
                    "bb — Session Expired",
                    "Run `bb auth` to re-authenticate.",
                    priority="high",
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
            console.print(
                f"[green]✔[/green] {g_new3} grades new from grades page "
                f"[{time.monotonic()-_t3:.1f}s]"
            )
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
        console.print(
            f"[green]✔[/green] {c_new5} content additions new [{time.monotonic()-_t5:.1f}s]"
        )
    except SessionError:
        console.print("[yellow]⚠[/yellow] Session expired — run [bold]bb auth[/bold].")
    except Exception as exc:
        console.print(f"[yellow]⚠[/yellow] Content scan failed: {exc}")

    # --- Change digest (deadlines/grades modified since run_start) ---
    with Database(db_path) as db:
        db.setup()
        changes = db.get_changes(since=run_start)
        digest = _render_change_digest(changes)
        if digest:
            console.print(f"[cyan]{digest}[/cyan]")
            _notify_changes(db, changes, cfg.notification)

    # --- Notify ---
    if total_new > 0:
        label = f"{total_new} new item{'s' if total_new != 1 else ''} synced"
        dispatch_notify(cfg.notification, "bb", label)
        console.print(f"[blue]🔔[/blue] {label}")

    _run_proactive(cfg, db_path)  # again: Phase 2 may have found stream-only deadlines


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
        if interval_hours > 6:
            console.print(
                f"[yellow]⚠[/yellow] Syncing every {interval_hours}h can miss the 6-hour "
                "deadline reminder; 4h is recommended."
            )
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
    course = _course_arg(course)
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
        announcements = db.get_recent_announcements(limit=limit, unread_only=unread)

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

            title = escape(a.title)
            title_str = f"[bold]{title}[/bold]" if a.read_at is None else title
            if a.body:
                preview = escape(a.body[:120] + ("…" if len(a.body) > 120 else ""))
                title_str += f"\n[dim]{preview}[/dim]"
            table.add_row(a.course, title_str, posted_str)

        console.print(table)
        # Listing an announcement in `bb ann` counts as reading it.
        db.mark_announcements_read([a.id for a in announcements if a.read_at is None])


@app.command()
def changes(
    show_all: bool = typer.Option(False, "--all", help="Show full history (does not mark seen)"),
    course: Optional[str] = typer.Option(None, "--course", "-c", help="Filter by course code"),
    days: int = typer.Option(30, "--days", "-d", help="Look back N days"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON array"),
) -> None:
    """Show what changed on Blackboard (moved deadlines, posted/changed grades)."""
    course = _course_arg(course)
    BB_DIR = _config_module.BB_DIR
    with Database(BB_DIR / "bb.db") as db:
        db.setup()
        rows = db.get_changes(
            days=days, course=course,
            unacknowledged_only=not show_all,
        )
        if output_json:
            import json

            console.print(json.dumps([
                {
                    "course": c.course, "item_type": c.item_type,
                    "title": c.title, "change_type": c.change_type,
                    "old_value": c.old_value, "new_value": c.new_value,
                    "detected_at": c.detected_at,
                }
                for c in rows
            ]))
            return
        if not rows:
            console.print("[dim]No changes.[/dim]" if show_all
                          else "[dim]Nothing new since you last checked.[/dim]")
            return
        from bb.changes import humanize

        console.print(humanize(rows))
        if not show_all:
            db.acknowledge_changes([c.id for c in rows if c.id is not None])


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
    course_code = _course_arg(course_code) or course_code.upper()
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


@app.command()
def download(
    course_code: str = typer.Argument(..., help="Course code, e.g. BTP200"),
    all_files: bool = typer.Option(False, "--all", help="Download all downloadable files"),
    file_type: str | None = typer.Option(None, "--type", help="Filter by type: pdf, html, etc."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be downloaded"),
    item_name: str | None = typer.Argument(None, help="Specific item name (substring match)"),
) -> None:
    """Download course files to ~/.bb/files/<COURSE>/."""
    course_code = _course_arg(course_code) or course_code.upper()
    import bb.cache as cache
    from bb.security.session import SessionManager

    BB_DIR = _config_module.BB_DIR
    tree = cache.load_tree(course_code)
    if tree is None:
        console.print(
            f"[red]✘[/red] No cache for [bold]{course_code.upper()}[/bold]. "
            f"Run [bold]bb course {course_code.upper()}[/bold] first."
        )
        raise typer.Exit(1)

    candidates = collect_downloadable(tree.items)

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
            ext = ext_from_url(item.download_url).lstrip(".")
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
            ext = ext_from_url(item.download_url)
            console.print(f"  {item.title}{ext}")
        raise typer.Exit(0)

    dest_dir = BB_DIR / "files" / course_code.upper()
    sm = SessionManager(BB_DIR / "session.enc")
    downloader = Downloader(sm)

    console.print(f"📥 [bold]{course_code.upper()}[/bold] — Downloading files")

    def _show(kind: str, name: str, detail: str) -> None:
        if kind == "skipped":
            console.print(f"  [dim]⏩ {name}  {detail}[/dim]")
        elif kind == "saved":
            console.print(f"  [green]✔[/green] {name}  {detail}")
        else:
            console.print(f"  [yellow]⚠[/yellow]  {name}  {detail}")

    with Database(BB_DIR / "bb.db") as db:
        db.setup()
        report = download_items(candidates, course_code, dest_dir, downloader, db, on_event=_show)

    console.print(
        f"[green]✔[/green] {len(report.saved)} downloaded, {len(report.skipped)} skipped, "
        f"{len(report.failed)} failed  →  [dim]{dest_dir}[/dim]"
    )


@app.command(name="open")
def open_item(
    course_code: str = typer.Argument(..., help="Course code, e.g. BTP200"),
    item_name: str = typer.Argument(..., help="Item title (substring match)"),
) -> None:
    """Open a course item in the browser."""
    course_code = _course_arg(course_code) or course_code.upper()
    import bb.cache as cache
    from bb.models.content import find_items

    tree = cache.load_tree(course_code)
    if tree is None:
        console.print(
            f"[red]✘[/red] No cache for [bold]{course_code.upper()}[/bold]. "
            f"Run [bold]bb course {course_code.upper()}[/bold] first."
        )
        raise typer.Exit(1)

    matches = find_items(tree.items, item_name)

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


def _auth_if_needed() -> None:
    """Skip the browser login when the saved session is still fresh (re-running setup)."""
    from bb.security.session import SessionManager

    sm = SessionManager(_config_module.BB_DIR / "session.enc")
    if sm.check_session_age() == "fresh":
        console.print("[green]✔[/green] Already logged in.")
        return
    auth()


def _print_ai_status() -> None:
    from bb.ai.providers.ollama import get_model, is_available

    model = get_model(load_config().ai.model) if is_available() else None
    if model:
        console.print(f"[green]✔[/green] AI ready: {model} — try [bold]bb chat[/bold]")
    else:
        console.print(
            "[yellow]⚠[/yellow] No local AI yet (optional, only needed for bb chat): "
            "install https://ollama.com then run [bold]ollama pull qwen3:8b[/bold]"
        )


def _first_sync_succeeded(since: str) -> bool:
    """True if a sync_log row without an error was written at/after `since` (ISO UTC)."""
    with Database(_config_module.BB_DIR / "bb.db") as db:
        db.setup()
        row = db._conn.execute(
            "SELECT 1 FROM sync_log WHERE error IS NULL AND synced_at >= ? LIMIT 1", (since,)
        ).fetchone()
    return row is not None


@app.command()
def setup() -> None:
    """One command to get going: settings → browser → login → first sync → auto-sync."""
    started = datetime.now(timezone.utc).isoformat()
    steps = [
        ("1/4 Settings", init),
        ("2/4 Browser", setup_browsers),
        ("3/4 Blackboard login", _auth_if_needed),
        ("4/4 First sync", lambda: sync(ical_only=False, dry_run=False, refresh_only=False)),
    ]
    for label, step in steps:
        console.rule(f"[bold]{label}[/bold]")
        try:
            step()
        except (typer.Exit, typer.Abort, KeyboardInterrupt) as exc:
            if not isinstance(exc, typer.Exit) or exc.exit_code:
                console.print(
                    f"[red]✘[/red] {label} failed. Fix the error above, then run "
                    "[bold]bb setup[/bold] again (finished steps are safe to repeat)."
                )
                raise

    if not _first_sync_succeeded(started):
        console.print(
            "[red]✘[/red] First sync didn't succeed — fix the errors above, then run "
            "[bold]bb setup[/bold] again."
        )
        raise typer.Exit(1)

    if typer.confirm("Sync automatically every few hours? (needed for reminders)", default=True):
        auto_setup(disable=False, interval=0)
    _print_ai_status()
    console.print("\n[green]✔ Done.[/green] Run [bold]bb[/bold] any time to see what's due.")
    console.print(
        "[dim]Tip: add your Blackboard iCal URL to Google/Apple Calendar to see deadlines "
        "there too.[/dim]"
    )


if __name__ == "__main__":
    app()
