# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`bb-cli` is "Claude Code for Blackboard" — a terminal-first tool that lets college students manage their entire school life without opening a browser. Core features: sync deadlines/grades/announcements from Blackboard Ultra, browse/download course content, and **`bb chat` — an interactive AI assistant** that answers questions using real Blackboard data. Think of it as giving students a personal AI that actually knows their courses, deadlines, and grades.

Target distribution: PyPI package `bb-cli`. Blackboard Ultra first, plugin architecture for Canvas/Moodle/Brightspace later.

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

# Start MCP server (for Claude Desktop integration)
uv run bb mcp-server
```

## Architecture

### Core Data Flow

```
bb sync
  → Phase 1: iCal feed (no auth) via httpx
  → Phase 2: Activity Stream scraping via Playwright (headed Chromium)
  → Parse → upsert to SQLite (~/.bb/bb.db)
  → Notify via configured provider(s)

bb chat
  → User types natural language query
  → LLM decides which tool functions to call
  → Tool functions query local DB / read cached files / trigger sync
  → LLM formats response with real data
  → Never hallucinate — always ground answers in tool results

bb mcp-server
  → Exposes tool functions as MCP protocol tools
  → Claude Desktop / Cursor / any MCP client can connect
  → Student asks Claude "what are my deadlines?" → Claude calls bb-cli tools → real data
```

### Project Structure

```
bb/
  cli.py            # Typer app — all command definitions
  config.py         # TOML config at ~/.bb/config.toml (Pydantic validation)
  db.py             # SQLite (WAL mode) — CRUD + version-based migrations
  sync.py           # Orchestrates both sync phases
  hash.py           # Content hashing utilities for dedup
  logger.py         # Structured logging with Rich handler
  adapters/
    base.py         # LMSAdapter ABC — defines interface all adapters must implement
    registry.py     # Decorator-based adapter registration + discovery
    blackboard_ultra.py  # Playwright scraping: auth, activity stream, grades, content
  parsers/
    ical.py         # .ics → list[Deadline], UTC storage / Toronto display
    html_llm.py     # LLM-based HTML parser — fallback when CSS selectors fail
  security/
    session.py      # Fernet-encrypted session files; keyring for key storage
  notify/
    base.py         # Notifier ABC
    terminal.py     # OS-native notifications (osascript / notify-send)
    ntfy.py         # ntfy.sh push (zero account required)
    telegram.py     # Telegram Bot API
    discord.py      # Discord webhook
  tools/
    __init__.py     # TOOL_REGISTRY — central dict of all callable tool functions
    queries.py      # DB query tools: deadlines, grades, announcements, courses
    ai_tools.py     # AI-powered tools: summarize, study plan, key concepts
  ai/
    chat.py         # Chat engine: REPL loop, tool calling orchestration, streaming
    prompts.py      # System prompt for student assistant context
    providers/
      ollama.py     # Ollama local LLM integration (free, private, offline)
      api.py        # Claude API / OpenAI API fallback
  mcp/
    server.py       # MCP server exposing tool functions for Claude Desktop
  models/
    content.py      # ContentItem, ContentTree dataclasses for course browser
  cache.py          # TTL-based content cache management
selectors/
  blackboard_ultra.toml   # CSS selectors loaded at runtime — NOT hardcoded
tests/
  fixtures/
    sample.ics
    activity_stream.html  # Saved real HTML for offline testing
```

### Key Design Decisions

**`bb chat` is the killer feature.** Everything else (sync, due, grades) is foundation that chat builds on. The tool function layer (`bb/tools/`) is the bridge: CLI commands and chat both call the same functions, just with different interfaces.

**Tool function architecture.** Every data query is a tool function in `bb/tools/queries.py` with: clear docstring (LLM reads this), Pydantic input/output models, and direct SQLite queries. The LLM calls these tools — it never makes up data. Tool functions are shared between `bb chat` (Ollama/API calls them) and `bb mcp-server` (Claude Desktop calls them via MCP protocol).

**AI provider priority.** `bb chat` auto-detects: Ollama running locally → use it (free, private, offline). No Ollama → check config for Claude/OpenAI API key → use that. No AI at all → graceful message suggesting install Ollama. Config: `[ai] provider = "ollama" | "claude" | "openai"` in `~/.bb/config.toml`.

**MCP server as Claude Desktop bridge.** `bb mcp-server` starts a stdio MCP server that exposes all tool functions. Students add it to Claude Desktop config → can ask Claude about their Blackboard data in natural language. This means bb-cli works both standalone (via `bb chat` with Ollama) and as a plugin for Claude Desktop.

**Selector externalization.** All Playwright CSS selectors live in `selectors/blackboard_ultra.toml`. The adapter reads them at runtime. This allows selector updates without code changes when Blackboard modifies its UI.

**Selector resilience.** Primary selector → fallback selector → LLM extraction (`bb/parsers/html_llm.py` using Ollama locally). Circuit breaker: max 20 pages per sync.

**Session encryption.** Playwright `storage_state()` is encrypted with Fernet symmetric encryption. Key stored in OS keyring; falls back to password-based derivation when keyring is unavailable.

**Session 3-tier check.** fresh (< threshold, skip verify) / uncertain (verify with headless browser) / expired (assume dead) — ported from SkipClass Pro's `smart_session_manager.py`.

**Cache layer.** Course content trees cached at `~/.bb/cache/<COURSE>/tree.json` with 2h TTL. Downloads at `~/.bb/files/<COURSE>/`. Study packs at `~/.bb/study/<COURSE>/`.

### Data Models

Defined in `bb/adapters/base.py`:
- `Deadline` — course, title, due_at (UTC), source (ical/stream/api)
- `Announcement` — course, title, body_preview, posted_at, is_read
- `GradeItem` — course, item, score, out_of, status (pending/submitted/graded)

Content models in `bb/models/content.py`:
- `ContentItem` — type (module/file/folder/discussion/link), title, url, download_url, children, size_bytes, mime_type
- `ContentTree` — course, scraped_at, items list

Tool output models in `bb/tools/`:
- All tool functions return plain dicts or Pydantic models serializable to JSON
- LLM receives tool results as JSON → formats human-readable response

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
| `bb init` | Interactive wizard — LMS URL, notification method, AI provider, saves `~/.bb/config.toml` |
| `bb auth` | Opens headed Chromium for login + MFA, saves encrypted session |
| `bb sync` | Full sync (iCal + Activity Stream); `--ical-only`, `--dry-run` flags |
| `bb due` | Upcoming deadlines table; `--days N`, `--course`, `--all`, `--json` |
| `bb ann` | Recent announcements; `--unread` filter |
| `bb grades` | Grade table; `--course` filter |
| `bb status` | Session health, last sync time, DB stats |
| `bb chat` | **Interactive AI assistant** — ask anything about your courses in natural language |
| `bb chat "query"` | Single-shot mode — ask one question, get answer, exit |
| `bb <COURSE>` | Interactive course content browser (e.g., `bb BTP200`); `--tree`, `--refresh` |
| `bb download <COURSE>` | File downloader; `--all`, `--type pdf` flags |
| `bb open <COURSE> <item>` | Open non-downloadable items in browser |
| `bb mcp-server` | Start MCP server for Claude Desktop / Cursor integration |
| `bb auto-setup` | Install OS scheduler for automatic syncing; `--disable` to stop |
| `bb cache clear` | Clear content cache |
| `bb setup-browsers` | Run `playwright install chromium` |

### `bb chat` Special Commands

Inside the chat REPL, these slash commands are available:
- `/exit` or `/quit` — exit chat
- `/clear` — clear conversation history
- `/sync` — trigger `bb sync` without leaving chat
- `/courses` — list all courses
- `/help` — show available commands

## Testing Approach

- Use real in-memory SQLite (not mocks) for DB tests
- Save real Blackboard HTML as fixtures for offline adapter testing
- Mock Playwright for integration tests
- Mock Ollama for chat tests — test tool routing + response format
- Test tool functions independently with fixture data in SQLite
- Test MCP server for protocol compliance
- Target: >70% coverage before PyPI release
- Typer app must have 2+ commands — single-command apps collapse into standalone mode, breaking `runner.invoke(app, ["subcommand"])` in tests
- Patch `BB_DIR` in tests via `unittest.mock.patch("bb.config.BB_DIR", tmp_path)` and `patch("bb.db.BB_DIR", tmp_path)` — `Database.__init__` uses `path=None` pattern so `BB_DIR` is resolved at call time, not import time
- WAL pragma does nothing on `:memory:` — test WAL mode with a real `tempfile.NamedTemporaryFile`

## Gotchas & Environment Notes

- **Hatchling package discovery**: `pyproject.toml` requires `[tool.hatch.build.targets.wheel] packages = ["bb"]` — hatchling cannot auto-discover `bb` from the hyphenated project name `bb-cli`
- **uv dev deps syntax**: Use `[dependency-groups] dev = [...]` (PEP 735), NOT `[tool.uv] dev-dependencies` — the latter is deprecated and will break in future uv versions
- **SQLite migrations**: Use `connection.executescript()` (not `execute()`) for multi-statement SQL migration strings — handles multiple statements and auto-commits
- **CLI not found after uv sync**: If `uv run bb` gives `ModuleNotFoundError`, run `uv pip install -e .` to force editable install registration
- **`git filter-repo` removes remote**: After running `git filter-repo`, remote is deleted — re-add with `git remote add origin <url>` before force pushing
- **Ollama tool calling**: `qwen3:30b-a3b` is the recommended model — Qwen3 generation has significantly better tool calling accuracy than Qwen2.5. MoE architecture (3B active params) means it runs fast despite 30.5B total params. Always validate tool call arguments with Pydantic before executing. If tool calling fails, fall back to keyword-based routing.
- **MCP server stdio**: MCP server communicates via stdin/stdout (stdio transport). Do NOT print anything to stdout in server mode — use stderr for logging. Use `from mcp.server.fastmcp import FastMCP` — `FastMCP` lives inside the official `mcp` package (`mcp>=1.12`), not the third-party `fastmcp` package. Pass `log_level="WARNING"` to suppress INFO noise to stderr.
- **Chat streaming**: When streaming Ollama responses, use `rich.live.Live` context for smooth token-by-token display. Don't mix `print()` with Rich Live — it causes display glitches.
- **Tool function docstrings matter**: Ollama/Claude read tool docstrings to decide when to call them. Write docstrings as if explaining to a smart intern what the function does and when to use it.