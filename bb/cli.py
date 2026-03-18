from __future__ import annotations

import typer
from rich.console import Console

import bb.config as _config_module
from bb.config import BBConfig, NotificationConfig, load_config, save_config
from bb.db import Database

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
