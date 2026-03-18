# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`bb-cli` is a terminal CLI tool for Blackboard LMS (targeting Blackboard Ultra). It syncs deadlines, grades, and announcements, provides a course content browser, file downloader, and an AI-powered study optimizer. Target distribution: PyPI package `bb-cli`.

## Package Manager & Commands

This project uses `uv` exclusively — do not use `pip` directly.

```bash
# Run CLI commands
uv run bb <command>

# Run tests
uv run pytest tests/ -v
uv run pytest tests/test_db.py -v          # single test file
uv run pytest --cov=bb --cov-report=term-missing  # with coverage

# Watch mode during development
uv run ptw

# Linting and formatting
uv run ruff check bb/
uv run ruff format bb/

# Build package
uv build

# Install from local source
uv pip install -e .
```

## Architecture

### Core Data Flow

```
bb sync
  → Phase 1: iCal feed (no auth) via httpx
  → Phase 2: Activity Stream scraping via Playwright (headed Chromium)
  → Parse → upsert to SQLite (~/.bb/bb.db)
  → Notify via configured provider(s)
```

### Project Structure

```
bb/
  cli.py            # Typer app — all command definitions
  config.py         # TOML config at ~/.bb/config.toml (Pydantic validation)
  db.py             # SQLite (WAL mode) — CRUD + version-based migrations
  sync.py           # Orchestrates both sync phases
  adapters/
    base.py         # LMSAdapter ABC — defines interface all adapters must implement
    registry.py     # Decorator-based adapter registration + discovery
    blackboard_ultra.py  # Playwright scraping: auth, activity stream, grades, content
  parsers/
    ical.py         # .ics → list[Deadline], UTC storage / Toronto display
    html.py         # LLM-based HTML parser — fallback when CSS selectors fail
  security/
    session.py      # Fernet-encrypted session files; keyring for key storage
  notify/
    base.py         # Notifier ABC
    terminal.py     # OS-native notifications (osascript / notify-send)
    ntfy.py         # ntfy.sh push (zero account required)
    telegram.py     # Telegram Bot API
    discord.py      # Discord webhook
  ai/
    optimizer.py    # Ollama (local) primary; Claude/GPT-4o-mini fallback
selectors/
  blackboard_ultra.toml   # CSS selectors loaded at runtime — NOT hardcoded
tests/
  fixtures/
    sample.ics
    activity_stream.html  # Saved real HTML for offline testing
```

### Key Design Decisions

**Selector externalization**: All Playwright CSS selectors live in `selectors/blackboard_ultra.toml`. The adapter reads them at runtime. This allows selector updates without code changes when Blackboard modifies its UI.

**Selector resilience**: Primary selector → fallback selector → LLM extraction (`bb/parsers/html.py` using Ollama locally). Circuit breaker: max 20 pages per sync.

**Session encryption**: Playwright `storage_state()` is encrypted with Fernet symmetric encryption. Key stored in OS keyring; falls back to password-based derivation when keyring is unavailable.

**Session 3-tier check**: fresh (< threshold) / uncertain (needs verification) / expired — port logic from `smart_session_manager.py` in SkipClass Pro.

**Cache layer**: Course content trees cached at `~/.bb/cache/<COURSE>/tree.json` with 2h TTL. Downloads at `~/.bb/files/<COURSE>/`. Study packs at `~/.bb/study/<COURSE>/study_pack.md`.

**AI optimizer**: Reads downloaded materials + syllabus → generates ranked study priorities + condensed notes. Pydantic-validated structured output; retry on malformed AI response.

### Data Models

Defined in `bb/adapters/base.py`:
- `Deadline` — course, title, due_at (UTC), source (ical/stream)
- `Announcement` — course, title, body, posted_at, read_at
- `GradeItem` — course, item, score, out_of, status

### Notification Rules

Configured in `~/.bb/config.toml`. Default: new deadline → normal priority; deadline <24h → high; new grade → high; session expired → high. Dedup via `notified_at` field in DB.

### Automation

`bb auto-setup` installs OS-native scheduler:
- macOS: launchd plist at `~/Library/LaunchAgents/com.bb-cli.sync.plist`
- Linux: crontab entry
- Default interval: every 4 hours, runs `bb sync` silently

## CLI Commands

| Command | Description |
|---------|-------------|
| `bb init` | Interactive wizard — LMS URL, notification method, saves `~/.bb/config.toml` |
| `bb auth` | Opens headed Chromium for login + MFA, saves encrypted session |
| `bb sync` | Full sync (iCal + Activity Stream); `--ical-only`, `--dry-run` flags |
| `bb due` | Upcoming deadlines table; `--days N`, `--course`, `--all`, `--json` |
| `bb ann` | Recent announcements; `--unread` filter |
| `bb grades` | Grade table; `--course` filter |
| `bb status` | Session health, last sync time, DB stats |
| `bb <COURSE>` | Interactive course content browser (e.g., `bb BTP200`) |
| `bb download <COURSE>` | File downloader; `--all`, `--type pdf` flags |
| `bb open <COURSE> <item>` | Open non-downloadable items in browser |
| `bb optimize <COURSE>` | AI study pack generation from downloaded materials |
| `bb study <COURSE>` | Render saved study pack; `--topic` filter |
| `bb auto-setup` | Install OS scheduler for automatic syncing |
| `bb cache clear` | Clear content cache |
| `bb setup-browsers` | Run `playwright install chromium` |

## Testing Approach

- Use real in-memory SQLite (not mocks) for DB tests
- Save real Blackboard HTML as fixtures for offline adapter testing
- Mock Playwright for integration tests
- Target: >70% coverage before PyPI release
