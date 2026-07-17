# bb-cli — Blackboard for your terminal

[![CI](https://github.com/Bruce1508/bb-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/Bruce1508/bb-cli/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/blackboard-cli.svg)](https://pypi.org/project/blackboard-cli/)
[![Downloads](https://img.shields.io/pypi/dw/blackboard-cli.svg)](https://pypi.org/project/blackboard-cli/)
[![Python](https://img.shields.io/pypi/pyversions/blackboard-cli.svg)](https://pypi.org/project/blackboard-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Stop opening Blackboard.** `bb` syncs your deadlines, grades, and announcements to a local database — then lets you ask an AI about them in plain English, right from your terminal.

```
$ bb chat "what do I have due this week?"
🤖 You have 3 deadlines this week:
   • BTP200 Lab 4 — tomorrow at 11:59 PM
   • INT222 Assignment 2 — Friday at 11:59 PM
   • OPS445 Quiz 3 — Friday at 11:59 PM
```

> **Status:** early alpha (`0.1.x`). Blackboard Ultra only. The AI assistant runs on a local Ollama model. See [Roadmap](#roadmap) for what's planned.

---

## Key features

- **Local sync** — deadlines (iCal + activity stream), grades, and announcements stored in SQLite at `~/.bb/bb.db`.
- **`bb chat`** — an AI assistant that answers questions using *your real Blackboard data*. It queries the local database via tools; it doesn't invent grades or dates.
- **Course browser & downloads** — browse a course's content tree and download files.
- **Claude Desktop integration** — exposes all query tools over MCP so you can ask Claude Desktop about your courses.
- **Notifications** — terminal-native alerts (and ntfy push) when new deadlines or grades appear.
- **Auto-sync** — install an OS scheduler (launchd/cron) to keep data fresh in the background.

## Tech stack

Python 3.11+ · [Typer](https://typer.tiangolo.com/) · [Rich](https://rich.readthedocs.io/) · [Playwright](https://playwright.dev/python/) (headed Chromium) · [Pydantic](https://docs.pydantic.dev/) · SQLite · [Ollama](https://ollama.com) · [MCP](https://modelcontextprotocol.io/)

---

## Install

### Step 1: Install the package

```bash
pip install blackboard-cli
```

> **Requires Python 3.11+** — check with `python3 --version`.
> Don't have it? Download from [python.org/downloads](https://www.python.org/downloads/) or run `brew install python@3.11` (macOS).

### Step 2: Install the browser

> **Important:** `bb auth` and `bb sync` drive a Chromium browser to scrape Blackboard.
> Run this once after install — it downloads ~170 MB.

```bash
bb setup-browsers
```

### Step 3: Set up and sync

```bash
bb init    # first-time setup — LMS URL, notification preferences, AI provider
bb auth    # log in to Blackboard (opens a browser window)
bb sync    # sync deadlines, grades, and announcements
bb due     # show what's coming up
bb chat    # open the AI assistant
```

That's it — your deadlines, grades, and announcements are now in your terminal, with an AI that can read them.

---

## Commands

| Command | Description |
|---------|-------------|
| `bb init` | First-time setup wizard |
| `bb auth` | Log in to Blackboard (headed browser) |
| `bb sync` | Sync all data (`--ical-only`, `--dry-run`, `--refresh-only`) |
| `bb import-ical <URL>` | Import deadlines from a Blackboard iCal feed (`--dry-run`) |
| `bb due` | Upcoming deadlines table (`--days 14`, `--course BTP200`) |
| `bb grades` | Grade table (`--course BTP200`) |
| `bb ann` | Recent announcements (`--unread`) |
| `bb status` | Session health, last sync, DB stats |
| `bb chat` | AI assistant — ask anything about your courses |
| `bb course <COURSE>` | Browse course content (e.g. `bb course BTP200`; `--tree`, `--refresh`) |
| `bb download <COURSE>` | Download course files (`--all`, `--type pdf`) |
| `bb open <COURSE> <item>` | Open a course item in your browser |
| `bb mcp-server` | Start MCP server for Claude Desktop |
| `bb auto-setup` | Install/remove OS-native auto-sync (`--disable`) |
| `bb cache-clear [COURSE]` | Clear cached course content |
| `bb setup-browsers` | Install Chromium for scraping |
| `bb version` | Print the installed version |

---

## `bb chat` — Ask your AI anything

`bb chat` is an interactive AI assistant that knows your real Blackboard data. It never makes up grades or deadlines — it queries your local database through tool functions. Responses stream token-by-token.

```bash
$ bb chat
🎓 bb chat — ask me anything about your courses
Type /help for commands, /exit to quit

You: do I have anything due tomorrow?
🤖 Yes — BTP200 Lab 4 is due tomorrow at 11:59 PM.

You: generate a study plan for my INT222 exam on Friday
🤖 Here's a 3-day study plan for INT222...

You: /sync
🔄 Syncing...
✓ Sync complete.
```

**Slash commands inside chat:** `/help`, `/exit` (or `/quit`), `/clear`, `/sync`, `/courses`.

**AI provider.** `bb chat` uses a local [Ollama](https://ollama.com) model — free, private, and offline. Install Ollama, then pull a model with good tool-calling support:

```bash
ollama pull qwen3:8b
```

`bb chat` auto-detects an available Ollama model. If none is found, it prints setup guidance and exits. Hosted providers (Claude / OpenAI) are on the [Roadmap](#roadmap) and not yet implemented.

---

## Claude Desktop integration (MCP)

`bb mcp-server` exposes all 13 bb-cli query tools over the Model Context Protocol, so you can ask Claude Desktop about your deadlines and grades without leaving your AI chat.

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "bb-cli": {
      "command": "bb",
      "args": ["mcp-server"]
    }
  }
}
```

Claude Desktop then has access to deadlines, grades, announcements, course content, file reads, and the AI study tools.

---

## Configuration

`~/.bb/config.toml` is created by `bb init`. Example:

```toml
lms_type = "blackboard_ultra"
lms_url  = "https://your-school.blackboard.com"

[ai]
provider = "ollama"   # only "ollama" is supported today
model    = ""         # "" = auto-detect the best available Ollama model
think    = false      # true = chain-of-thought (slower, deeper); false = fast

[notification]
provider   = "terminal"  # terminal | ntfy  (telegram/discord: planned)
ntfy_topic = ""          # required when provider = "ntfy"
```

`ical_url` is saved automatically after your first `bb import-ical` run.

---

## Notifications

`bb` can notify you when new deadlines or grades appear:

- **Terminal** — macOS/Linux native notifications (no setup).
- **ntfy** — push to any device via [ntfy.sh](https://ntfy.sh) (no account needed); set `ntfy_topic` in config.
- **Telegram / Discord** — planned; currently a no-op if configured.

---

## Auto-sync

Keep your data fresh automatically:

```bash
bb auto-setup           # installs launchd (macOS) or crontab (Linux)
bb auto-setup --disable # removes the scheduler
```

Default: syncs every 4 hours silently in the background.

---

## Roadmap

- Canvas, Moodle, and Brightspace adapters (Blackboard Ultra only today).
- Hosted AI providers (Claude / OpenAI) as an alternative to local Ollama.
- Telegram and Discord notification delivery.

### Known limitations

- **Blackboard Ultra only.**
- **`bb download` requires direct file links** — courses using Blackboard's "Document" page format show "no downloadable files". Use `bb open <COURSE> <item>` to open those in a browser.
- **Sessions expire (~24h)** — re-run `bb auth` when prompted.
- **Windows** — core commands work, but native desktop notifications aren't supported (use ntfy instead).

---

## Development

```bash
git clone https://github.com/Bruce1508/bb-cli
cd bb-cli
uv sync --all-groups    # install deps (incl. dev group)
uv run playwright install chromium
uv run pytest tests/    # run tests
uv run bb --help        # run the CLI
```

Requirements: Python 3.11+ and [uv](https://docs.astral.sh/uv/).

### Project layout

```
bb/
  cli.py            # Typer commands
  config.py         # ~/.bb/config.toml (Pydantic)
  db.py             # SQLite persistence + migrations
  sync.py           # iCal + activity-stream sync
  adapters/         # Blackboard Ultra scraping
  parsers/          # iCal + HTML parsing
  notify/           # terminal / ntfy notifiers
  tools/            # AI-facing query tools (shared by chat + MCP)
  ai/               # chat engine + Ollama provider
  mcp/              # MCP server
selectors/          # externalized CSS selectors
tests/              # pytest suite + fixtures
```

---

## Contributing

Issues and pull requests are welcome. Please run `uv run pytest tests/` and `uv run ruff check bb/` before opening a PR. See [Issues](https://github.com/Bruce1508/bb-cli/issues) for open work.

---

## License

MIT — see [LICENSE](LICENSE).

---

*Built for Seneca Polytechnic students. Works with any Blackboard Ultra institution.*
